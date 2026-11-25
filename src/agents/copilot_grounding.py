"""Verify and render claims over already authorized deterministic results."""

from collections.abc import Iterable

from src.models.copilot import WhyAnswer, WhyStatus
from src.models.copilot_integration import GroundedClaim, ParseSource, WhatIfReply, WhyReply
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
