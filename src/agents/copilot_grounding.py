"""Verify and render claims over already authorized deterministic results."""

from collections.abc import Iterable
from datetime import datetime
from typing import Literal

from src.models.copilot import WhyAnswer, WhyStatus
from src.models.copilot_integration import GroundedClaim, HowToReply, ParseSource, WhatIfReply, WhyReply
from src.models.recommendation import (
    EarliestCompletionForTarget,
    Feasibility,
    MaxSocByDeadline,
    MinTestedSiteLimitForSla,
    RecommendationEvidence,
    RecommendationResult,
)
from src.models.what_if import StationMetrics, WhatIfResult

METRICS = {
    "horizon_battery_kwh": "kWh battery",
    "horizon_output_kwh": "kWh charger output",
    "horizon_grid_input_kwh": "kWh grid input",
    "horizon_energy_cost_vnd": "VND",
    "peak_charger_output_kw": "kW charger output",
    "peak_grid_input_kw": "kW grid input",
    "unmet_original_battery_kwh": "kWh battery at cutoff",
    "unmet_original_output_kwh": "kWh charger output at cutoff",
    "plug_wait_mean_minutes": "min",
    "plug_wait_p90_minutes": "min",
    "charge_wait_mean_minutes": "min",
    "charge_wait_p90_minutes": "min",
    "service_coverage_rate": "fraction",
    "charged_coverage_rate": "fraction",
    "sla.on_time_rate": "fraction",
    "sla.AC.on_time_rate": "fraction",
    "sla.DC.on_time_rate": "fraction",
}


class GroundingError(ValueError):
    """A claim or its source is inconsistent with the authorized evidence."""


def _metric(metrics: StationMetrics, name: str) -> tuple[int | float | None, str]:
    match name.split("."):
        case ["sla", field]:
            return getattr(metrics.sla, field), f"sla/{field}"
        case ["sla", zone, field]:
            return getattr(metrics.by_zone[zone], field), f"by_zone/{zone}/{field}"
        case _:
            return getattr(metrics, name), name


class GroundingGate:
    """Use exact claim projection with trusted IDs and no unverified prose channel."""

    def __init__(self, claims: Iterable[GroundedClaim]) -> None:
        self.claims = tuple(claims)
        self._authorized = {claim.claim_id: claim for claim in self.claims}
        if len(self._authorized) != len(self.claims):
            raise GroundingError("Duplicate evidence claim identifiers")

    def verify(self, candidate: GroundedClaim) -> GroundedClaim:
        canonical = self._authorized.get(candidate.claim_id)
        if canonical is None or canonical.model_dump_json() != candidate.model_dump_json():
            raise GroundingError("Claim differs from authorized evidence")
        return canonical

    @classmethod
    def for_why(cls, answer: WhyAnswer) -> "GroundingGate":
        refs = {ref.ref_id: ref for ref in answer.evidence_refs}
        facts = {fact.fact_id: fact for fact in answer.facts}
        claims: list[GroundedClaim] = []
        for fact in answer.facts:
            sources = tuple(dict.fromkeys([fact.evidence_ref, *fact.input_evidence_refs]))
            if any(key not in refs or refs[key].correlation_id != fact.correlation_id for key in sources):
                raise GroundingError("Unresolved WHY fact reference")
            claims.append(
                GroundedClaim(
                    claim_id=fact.fact_id,
                    name=fact.name,
                    subject=fact.subject,
                    value=fact.value,
                    unit=fact.unit,
                    stage=fact.stage,
                    observed_at=fact.decided_at,
                    interval_start=fact.interval_start,
                    interval_end=fact.interval_end,
                    evidence_refs=sources,
                )
            )
        for i, reason in enumerate(answer.reasons):
            if (
                not reason.evidence_refs
                or any(
                    key not in refs or refs[key].correlation_id != reason.correlation_id for key in reason.evidence_refs
                )
                or any(
                    key not in facts or facts[key].correlation_id != reason.correlation_id for key in reason.fact_refs
                )
            ):
                raise GroundingError("Unresolved WHY reason reference")
            # G2 owns reason-code semantics and the deterministic summary for each template.
            claims.append(
                GroundedClaim(
                    claim_id=f"reason:{i}",
                    name=reason.template_key,
                    subject=reason.subject,
                    value=reason.summary,
                    stage="observed",
                    observed_at=reason.decided_at,
                    evidence_refs=tuple(reason.evidence_refs),
                    reason_code=reason.code,
                    reason_category=reason.category,
                )
            )
        return cls(claims)

    @classmethod
    def for_what_if(cls, result: WhatIfResult, station_id: str) -> "GroundingGate":
        if result.status == "completed":
            if (
                result.delta is None
                or result.delta_reasons is None
                or result.baseline.status != "completed"
                or result.patched.status != "completed"
                or not result.baseline.observed_until == result.patched.observed_until == result.horizon_end
            ):
                raise GroundingError("Comparison does not have a common safe horizon")
        elif result.delta is not None or result.delta_reasons is not None or result.feasible is not False:
            raise GroundingError("Unsafe or incomplete result carries a usable comparison")

        prefix = f"what-if:{result.snapshot_digest}:{result.patched.run_id}"
        claims = []
        for name, unit in METRICS.items():
            a, path = _metric(result.baseline.metrics, name)
            b, _ = _metric(result.patched.metrics, name)
            for side, value, branch in (("baseline", a, result.baseline), ("patched", b, result.patched)):
                claims.append(
                    GroundedClaim(
                        claim_id=f"{side}:{name}",
                        subject=station_id,
                        name=name,
                        value=value,
                        unit=unit,
                        stage="simulated",
                        observed_at=branch.observed_until,
                        interval_start=result.snapshot_time,
                        interval_end=branch.observed_until,
                        branch=side,
                        evidence_refs=(f"{prefix}#/{side}/metrics/{path}",),
                    )
                )
            if result.delta is None:
                continue
            if name not in result.delta:
                raise GroundingError("Comparison omitted a supported metric")
            delta = result.delta[name]
            reason = result.delta_reasons.get(name)
            if delta is None:
                if reason is None or (reason.code == "missing_data" and a is not None and b is not None):
                    raise GroundingError("Null delta lacks the corresponding evidence")
            elif a is None or b is None or reason is not None or delta != round(b - a, 6):
                raise GroundingError("Invalid signed delta")
            claims.append(
                GroundedClaim(
                    claim_id=f"delta:{name}",
                    subject=station_id,
                    name=name,
                    value=delta,
                    unit=unit,
                    stage="simulated",
                    observed_at=result.horizon_end,
                    interval_start=result.snapshot_time,
                    interval_end=result.horizon_end,
                    branch="delta",
                    direction="patched_minus_baseline",
                    reason_code=reason.code if reason else None,
                    evidence_refs=(
                        f"{prefix}#/baseline/metrics/{path}",
                        f"{prefix}#/patched/metrics/{path}",
                        f"{prefix}#/delta/{name}",
                    ),
                )
            )
        return cls(claims)

    @classmethod
    def for_how_to(cls, result: RecommendationResult, station_id: str) -> "GroundingGate":
        goal = result.goal
        subject = station_id if isinstance(goal, MinTestedSiteLimitForSla) else goal.booking_id
        claims = []

        def add_projection(
            key: str,
            side: Literal["baseline", "candidate"],
            evidence: RecommendationEvidence,
        ) -> None:
            def add(
                pointer: str,
                value: bool | float | int | str | datetime | None,
                unit: str | None = None,
                observed_at: datetime | None = None,
                *,
                claim_subject: str = subject,
            ) -> None:
                claims.append(
                    GroundedClaim(
                        claim_id=f"{key}:{pointer}",
                        subject=claim_subject,
                        name=pointer,
                        value=value.isoformat() if isinstance(value, datetime) else value,
                        unit=unit,
                        stage="simulated",
                        branch=side,
                        observed_at=observed_at or evidence.observed_until,
                        evidence_refs=(f"{evidence.ref}#{pointer}",),
                    )
                )

            for field in ("branch_status", "blocked_commands", "pending_approvals", "hard_violations"):
                add(f"/{field}", getattr(evidence, field))
            if evidence.original_sla is not None:
                add("/original_sla/on_time_rate", evidence.original_sla.on_time_rate, "fraction")
                add("/original_sla/denominator", evidence.original_sla.denominator, "bookings")
                for index, row in enumerate(evidence.booking_sla):
                    add(
                        f"/booking_sla/{index}/original/met_deadline",
                        row.original.met_deadline,
                        observed_at=min(row.original.deadline, evidence.observed_until),
                        claim_subject=row.booking_id,
                    )
            for key_name in ("subject_original", "subject_revised"):
                outcome = getattr(evidence, key_name)
                if outcome is None:
                    continue
                add(f"/{key_name}/target_soc", outcome.target_soc, "%")
                add(f"/{key_name}/deadline", outcome.deadline)
                add(
                    f"/{key_name}/met_deadline",
                    outcome.met_deadline,
                    observed_at=min(outcome.deadline, evidence.observed_until),
                )
                add(f"/{key_name}/target_reached_at", outcome.target_reached_at, observed_at=outcome.target_reached_at)
            if evidence.subject_goal_target is not None:
                target = evidence.subject_goal_target
                add("/subject_goal_target/target_soc", target.target_soc, "%")
                add(
                    "/subject_goal_target/target_reached_at",
                    target.target_reached_at,
                    observed_at=target.target_reached_at,
                )
            if evidence.subject_soc_observed_at is not None:
                add(
                    "/subject_soc_at_deadline_pct",
                    evidence.subject_soc_at_deadline_pct,
                    "%",
                    evidence.subject_soc_observed_at,
                )
                add(
                    "/subject_soc_observed_at",
                    evidence.subject_soc_observed_at,
                    observed_at=evidence.subject_soc_observed_at,
                )
            if not isinstance(goal, MinTestedSiteLimitForSla):
                add("/subject_release_at", evidence.subject_release_at, observed_at=evidence.subject_release_at)

        if result.baseline:
            add_projection("baseline", "baseline", result.baseline)
        for index, branch in enumerate(result.candidates):
            if branch.evidence:
                add_projection(f"candidate:{index}", "candidate", branch.evidence)
        for option in result.options:
            if (
                option not in result.candidates
                or option.feasibility != Feasibility.FEASIBLE
                or option.evidence is None
                or option.evidence.branch_status != "completed"
                or option.evidence.hard_violations
                or option.evidence.blocked_commands
                or option.evidence.pending_approvals
                or option.evidence.pending_approval_commands
                or option.evidence.rejected_allocations
                or option.evidence.unresolved_safety_count
                or option.evidence.safety_holds
            ):
                raise GroundingError("Ranked option lacks a safe feasible branch")
        return cls(claims)


def render_how_to(result: RecommendationResult, station_id: str) -> HowToReply:
    gate = GroundingGate.for_how_to(result, station_id)
    goal, baseline = result.goal, result.baseline
    option = result.options[0] if result.options else None
    evidence = option.evidence if option else None
    if result.unsupported_reason:
        summary = "Nguồn cấp độc lập nằm ngoài phạm vi của mục tiêu công suất này."
    elif evidence is None or baseline is None or result.baseline_issue is not None:
        summary = "Chưa xác minh được phương án khả thi trong tập đã thử."
    elif isinstance(goal, MinTestedSiteLimitForSla):
        rate = baseline.original_sla.on_time_rate if baseline.original_sla else None
        summary = "Phương án đầu tiên có mức công suất thấp nhất trong các mức đã xác minh khả thi."
        if rate is not None and rate >= goal.min_original_on_time_rate:
            summary = "Kịch bản gốc đã đáp ứng mục tiêu đúng hạn. Có thể giữ nguyên. " + summary
    elif isinstance(goal, EarliestCompletionForTarget):
        original = baseline.subject_goal_target
        proposed = evidence.subject_goal_target
        a = original.target_reached_at if original else None
        b = proposed.target_reached_at if proposed else None
        if a is not None and b is not None and original.target_soc == proposed.target_soc == goal.target_soc:
            summary = (
                "Phương án đạt cùng mục tiêu pin sớm hơn kịch bản gốc."
                if b < a
                else "Kịch bản gốc đạt cùng mục tiêu pin ít nhất sớm bằng phương án thử. Có thể giữ nguyên."
            )
        else:
            summary = "Phương án khả thi với các điều kiện đã chọn. Xem thời điểm đạt mức pin và thời điểm nhả cổng."
    elif isinstance(goal, MaxSocByDeadline):
        a, b = baseline.subject_soc_at_deadline_pct, evidence.subject_soc_at_deadline_pct
        if (
            a is not None
            and b is not None
            and baseline.subject_soc_observed_at == evidence.subject_soc_observed_at == goal.deadline
        ):
            if b > a:
                summary = "Phương án đạt mức pin cao hơn tại cùng hạn."
            elif isinstance(option.value, (int, float)) and a >= option.value:
                summary = "Kịch bản gốc đã đạt mức pin kiểm chứng tại hạn này. Có thể giữ nguyên."
            else:
                summary = "Chưa xác minh được cải thiện mức pin tại hạn đã chọn."
        else:
            summary = "Phương án khả thi. Thiếu quan sát trên cùng mốc để xác nhận mức cải thiện."
    if result.search_status == "partial":
        summary += " Tìm kiếm còn một phần vì có nhánh chưa thể xác minh."
    return HowToReply(result=result, claims=gate.claims, summary=summary)


def render_why(answer: WhyAnswer, source: ParseSource | None = None) -> WhyReply:
    gate = GroundingGate.for_why(answer)
    summary = {
        WhyStatus.OK: "Đã tìm thấy bằng chứng cho câu hỏi.",
        WhyStatus.PARTIAL: "Bằng chứng hiện có chỉ trả lời được một phần.",
        WhyStatus.NO_DATA: "Chưa có đủ bằng chứng cho câu hỏi này.",
        WhyStatus.FORBIDDEN: "Bạn không có quyền xem dữ liệu này.",
        WhyStatus.UNSUPPORTED: "Chủ đề này chưa được hỗ trợ.",
    }[answer.status]
    return WhyReply(result=answer, claims=gate.claims, summary=summary, parse_source=source)


def render_what_if(result: WhatIfResult, station_id: str) -> WhatIfReply:
    gate = GroundingGate.for_what_if(result, station_id)
    if result.status != "completed":
        summary = "Một nhánh thiếu thời gian quan sát hoặc có vấn đề an toàn. Chưa thể so sánh."
    elif any(
        branch.pending_approvals or branch.pending_approval_commands for branch in (result.baseline, result.patched)
    ):
        summary = "Kết quả mô phỏng có điều kiện vì còn phê duyệt."
    elif result.hypothetical_infrastructure:
        summary = "Kết quả mô phỏng dựa trên giả định nâng cấp hạ tầng."
    else:
        summary = "Đã mô phỏng hai nhánh. Kết quả chỉ dùng để tham khảo."
    return WhatIfReply(result=result, claims=gate.claims, summary=summary)
