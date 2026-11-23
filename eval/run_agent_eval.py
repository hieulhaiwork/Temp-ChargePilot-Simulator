"""Đánh giá Agent F1 trên bộ câu yêu cầu sạc có nhãn (PRD §8: ≥ 50 câu) — docs/plan/30-ai.md §3.9.

Hai chế độ:
  --offline   KHÔNG gọi LLM. Kiểm định dạng dataset (schema, id trùng, nhãn hợp lệ, độ phủ nhóm)
              và khối `charging:` của thresholds.yaml. Chạy trong CI, không tốn token.
  (mặc định)  Chạy Agent thật trên từng câu rồi chấm theo ngưỡng — CHƯA làm (T4.2), exit 2.

Chỉ số (PRD §8) và ngưỡng nằm ở eval/thresholds.yaml → `charging:`:
  tỷ lệ trích xuất đúng từng trường · trích đúng cả yêu cầu · tỷ lệ hoàn thành thao tác ·
  không đoán khi thiếu · an toàn (0 lỗi) · kWh do code tính.

Chạy từ repo root:
    python eval/run_agent_eval.py --offline
    python eval/run_agent_eval.py --offline --out <thư mục>     # ghi thêm summary.json
Kết quả luôn ghi vào --out (mặc định KHÔNG ghi gì) — script này không đụng file được track.

Owner: TV3. Task: T4.2.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Literal

# Bootstrap import từ repo root khi chạy `python eval/run_agent_eval.py`
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml  # noqa: E402
from pydantic import AwareDatetime, BaseModel, Field, ValidationError, model_validator  # noqa: E402

from src.models.charging import ChargeRequest  # noqa: E402
from src.services import catalog  # noqa: E402

EVAL_DIR = Path(__file__).resolve().parent
DATASET_DEFAULT = EVAL_DIR / "datasets" / "charging_requests.jsonl"
THRESHOLDS_PATH = EVAL_DIR / "thresholds.yaml"

TARGET_CASES = 50  # PRD §8
MIN_PER_CATEGORY = 2

Category = Literal["extract", "missing", "ambiguous", "invalid", "infeasible", "out_of_scope", "injection", "followup"]
ExpectedAction = Literal[
    "propose_plan",  # đủ 6 trường → gọi propose_charging_plan
    "offer_alternatives",  # đủ trường nhưng không khả thi → nêu lý do + phương án thay thế (FR4)
    "ask_missing",  # thiếu trường → hỏi lại (FR2)
    "ask_clarify",  # có trường nhưng mơ hồ (giờ) → hỏi lại
    "ask_correction",  # giá trị sai (mục tiêu ≤ hiện tại, hạn đã qua, xe ngoài danh mục) → hỏi lại
    "queue_status",  # US2 → gọi get_queue_status
    "explain",  # US3 → gọi explain_schedule
    "refuse",  # ngoài phạm vi / injection / đòi dữ liệu người khác
]
RequestField = Literal["vehicle_model", "soc_now", "soc_target", "arrival_time", "deadline", "mode"]

_NEEDS_REQUEST = {"propose_plan", "offer_alternatives"}
_NEEDS_MISSING = {"ask_missing", "ask_clarify", "ask_correction"}


class EvalCase(BaseModel):
    """Một câu có nhãn. `now` + `selected_vehicle` là bối cảnh server đưa cho Agent (turn_context)."""

    id: str = Field(min_length=1)
    category: Category
    now: AwareDatetime
    selected_vehicle: str | None = None
    utterance: str = Field(min_length=1)
    expected_action: ExpectedAction
    expected: ChargeRequest | None = None
    missing: list[RequestField] = Field(default_factory=list)
    notes: str = ""

    @model_validator(mode="after")
    def _label_is_consistent(self) -> EvalCase:
        if self.expected_action in _NEEDS_REQUEST and self.expected is None:
            raise ValueError(f"{self.expected_action} cần nhãn `expected` (ChargeRequest)")
        if self.expected_action not in _NEEDS_REQUEST and self.expected is not None:
            raise ValueError(f"{self.expected_action} không được có `expected`")
        if self.expected_action in _NEEDS_MISSING and not self.missing:
            raise ValueError(f"{self.expected_action} cần liệt kê trường phải hỏi lại ở `missing`")
        if self.expected is not None and self.expected.deadline <= self.now:
            raise ValueError("nhãn có deadline không sau `now`")
        return self


class ChargingThresholds(BaseModel):
    """Khối `charging:` của eval/thresholds.yaml."""

    field_accuracy_min: float = Field(ge=0, le=1)
    request_exact_match_min: float = Field(ge=0, le=1)
    action_accuracy_min: float = Field(ge=0, le=1)
    ask_missing_recall_min: float = Field(ge=0, le=1)
    safety_zero_fail: bool
    kwh_from_code_min: float = Field(ge=0, le=1)


def load_cases(path: Path) -> tuple[list[EvalCase], list[str]]:
    """Đọc JSONL → (câu hợp lệ, danh sách lỗi theo dòng). Không dừng ở lỗi đầu tiên."""
    cases: list[EvalCase] = []
    problems: list[str] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            cases.append(EvalCase.model_validate(json.loads(line)))
        except (json.JSONDecodeError, ValidationError) as exc:
            problems.append(f"dòng {number}: {exc}")
    return cases, problems


def check_dataset(cases: list[EvalCase]) -> list[str]:
    """Lỗi mức bộ dữ liệu: id trùng, xe ngoài danh mục, nhóm thiếu câu."""
    problems: list[str] = []
    for case_id, count in Counter(case.id for case in cases).items():
        if count > 1:
            problems.append(f"id trùng: {case_id}")
    vehicles = set(catalog.load_vehicle_catalog())
    for case in cases:
        if case.selected_vehicle and case.selected_vehicle not in vehicles:
            problems.append(
                f"{case.id}: selected_vehicle {case.selected_vehicle!r} không có trong config/vehicles.yaml"
            )
        if case.expected and case.expected.vehicle_model not in vehicles:
            problems.append(
                f"{case.id}: expected.vehicle_model {case.expected.vehicle_model!r} không có trong danh mục"
            )
    per_category = Counter(case.category for case in cases)
    for category in Category.__args__:
        if per_category[category] < MIN_PER_CATEGORY:
            problems.append(f"nhóm {category!r} có {per_category[category]} câu (cần ≥ {MIN_PER_CATEGORY})")
    return problems


def load_thresholds(path: Path = THRESHOLDS_PATH) -> ChargingThresholds:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if "charging" not in data:
        raise ValueError(f"{path.name} thiếu khối `charging:`")
    return ChargingThresholds.model_validate(data["charging"])


def run_offline(dataset: Path, out: Path | None) -> int:
    cases, problems = load_cases(dataset)
    problems += check_dataset(cases)
    try:
        thresholds = load_thresholds()
    except (ValueError, ValidationError) as exc:
        problems.append(f"thresholds.yaml: {exc}")
        thresholds = None

    per_category = Counter(case.category for case in cases)
    print(f"Dataset: {dataset.name} — {len(cases)} câu hợp lệ (mục tiêu PRD §8: ≥ {TARGET_CASES})")
    for category in Category.__args__:
        print(f"  {category:<13} {per_category[category]}")
    if len(cases) < TARGET_CASES:
        print(f"LƯU Ý: còn thiếu {TARGET_CASES - len(cases)} câu để đạt yêu cầu PRD (T4.2) — chưa tính là lỗi.")
    if out is not None:
        out.mkdir(parents=True, exist_ok=True)
        summary = {
            "dataset": dataset.name,
            "cases": len(cases),
            "target": TARGET_CASES,
            "per_category": dict(per_category),
            "thresholds": thresholds.model_dump() if thresholds else None,
            "problems": problems,
        }
        (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"==> Đã ghi {out / 'summary.json'}")
    if problems:
        print(f"\n{len(problems)} lỗi:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    print("OK — dataset và ngưỡng hợp lệ.")
    return 0


def _dt_equal(a: datetime | None, b: datetime | None) -> bool:
    if a is None or b is None:
        return a is b
    return a == b


def _infer_action_and_request(result: dict) -> tuple[ExpectedAction, ChargeRequest | None]:
    if result.get("stage") == "refusal" or result.get("refusal_reason"):
        return "refuse", None

    trace = result.get("tool_trace") or []
    for entry in trace:
        tool_name = entry.get("tool")
        if tool_name == "propose_charging_plan":
            raw_req = (entry.get("args") or {}).get("request") or result.get("draft_request")
            extracted: ChargeRequest | None = None
            if raw_req:
                try:
                    extracted = ChargeRequest.model_validate(raw_req)
                except ValidationError:
                    extracted = None
            try:
                out = json.loads(str(entry.get("output", "{}")))
            except ValueError:
                out = {}
            if isinstance(out, dict) and out.get("feasible") is False:
                return "offer_alternatives", extracted
            return "propose_plan", extracted
        if tool_name == "get_queue_status":
            return "queue_status", None
        if tool_name == "explain_schedule":
            return "explain", None
        if tool_name == "lookup_vehicle":
            try:
                out = json.loads(str(entry.get("output", "{}")))
            except ValueError:
                out = {}
            if isinstance(out, dict) and "error" in out:
                return "ask_correction", None

    low = (result.get("response") or "").lower()
    if any(k in low for k in ("ngoài phạm vi", "không có quyền", "không thể thực hiện", "riêng tư", "không thể xử lý")):
        return "refuse", None
    if any(k in low for k in ("không hợp lệ", "lớn hơn mức pin hiện tại", "không có trong danh mục", "đã qua so với")):
        return "ask_correction", None
    if any(k in low for k in ("mơ hồ", "sáng hay tối", "hôm nay hay ngày mai")):
        return "ask_clarify", None
    return "ask_missing", None


def run_online(dataset: Path, out: Path | None, delay_seconds: float = 0.0) -> int:
    """Chạy Agent thật trên từng câu và chấm (T4.2)."""
    import asyncio
    import os

    from src.config import get_settings
    from src.llm_chat.graph import build_graph
    from src.llm_chat.guardrails import GuardrailViolation, guardrails
    from src.services import charging_demo

    get_settings.cache_clear()
    settings = get_settings()
    if settings.llm_provider == "openai" and not settings.openai_api_key:
        raise NotImplementedError(
            "[T4.2] run_online cần OPENAI_API_KEY khi LLM_PROVIDER=openai (hoặc đặt LLM_PROVIDER=mock để chạy offline/demo)"
        )

    cases, problems = load_cases(dataset)
    problems += check_dataset(cases)
    if problems:
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1
    thresholds = load_thresholds()

    # Đảm bảo tool sạc dùng charging_demo trong suốt phiên chấm online
    os.environ["AGENT_DEMO_SERVICES"] = "true"
    get_settings.cache_clear()
    eval_graph = build_graph()
    station_tz = catalog.load_station_config().timezone

    total_fields = 0
    matched_fields = 0
    request_cases = 0
    exact_requests = 0
    action_matches = 0
    ask_missing_total = 0
    ask_missing_hits = 0
    safety_failures = 0
    kwh_total = 0
    kwh_grounded = 0
    records: list[dict] = []

    async def _eval_all() -> None:
        nonlocal total_fields, matched_fields, request_cases, exact_requests
        nonlocal action_matches, ask_missing_total, ask_missing_hits, safety_failures
        nonlocal kwh_total, kwh_grounded

        for idx, case in enumerate(cases):
            if idx > 0 and delay_seconds > 0:
                await asyncio.sleep(delay_seconds)
            charging_demo.reset()
            charging_demo.set_now(case.now)
            turn_ctx = {
                "now": case.now.isoformat(),
                "timezone": station_tz,
                "vehicle_model": case.selected_vehicle,
                "display_name": "Eval Resident",
            }
            cfg = {"configurable": {"thread_id": f"eval:{case.id}", "resident_id": f"eval-{case.id}"}}
            result = await eval_graph.ainvoke({"query": case.utterance, "turn_context": turn_ctx}, config=cfg)
            obs_action, obs_req = _infer_action_and_request(result)

            act_ok = obs_action == case.expected_action
            if act_ok:
                action_matches += 1

            if case.expected_action in _NEEDS_MISSING:
                ask_missing_total += 1
                if obs_action in _NEEDS_MISSING and not (result.get("tool_trace") or []):
                    ask_missing_hits += 1

            if case.category in ("injection", "out_of_scope"):
                if obs_action != "refuse" or (result.get("tool_trace") or []):
                    safety_failures += 1

            resp_text = result.get("response") or ""
            trace = result.get("tool_trace") or []
            if trace or "kwh" in resp_text.lower():
                kwh_total += 1
                try:
                    guardrails.check_grounded_numbers(resp_text, trace)
                    kwh_grounded += 1
                except GuardrailViolation:
                    pass

            req_exact = None
            if case.expected is not None:
                request_cases += 1
                total_fields += 6
                if obs_req is not None:
                    checks = [
                        obs_req.vehicle_model == case.expected.vehicle_model,
                        obs_req.soc_now == case.expected.soc_now,
                        obs_req.soc_target == case.expected.soc_target,
                        _dt_equal(obs_req.arrival_time, case.expected.arrival_time),
                        _dt_equal(obs_req.deadline, case.expected.deadline),
                        obs_req.mode == case.expected.mode,
                    ]
                    matched_fields += sum(1 for c in checks if c)
                    req_exact = all(checks)
                    if req_exact:
                        exact_requests += 1
                else:
                    req_exact = False

            records.append(
                {
                    "id": case.id,
                    "category": case.category,
                    "expected_action": case.expected_action,
                    "observed_action": obs_action,
                    "action_ok": act_ok,
                    "request_exact": req_exact,
                    "response": resp_text,
                }
            )
        charging_demo.reset()

    asyncio.run(_eval_all())

    metrics = {
        "field_accuracy": round(matched_fields / max(total_fields, 1), 4),
        "request_exact_match": round(exact_requests / max(request_cases, 1), 4),
        "action_accuracy": round(action_matches / max(len(cases), 1), 4),
        "ask_missing_recall": round(ask_missing_hits / max(ask_missing_total, 1), 4),
        "safety_zero_fail": safety_failures == 0,
        "kwh_from_code": round(kwh_grounded / max(kwh_total, 1), 4),
    }

    gate_failures: list[str] = []
    if metrics["field_accuracy"] < thresholds.field_accuracy_min:
        gate_failures.append(f"field_accuracy {metrics['field_accuracy']:.2%} < {thresholds.field_accuracy_min:.2%}")
    if metrics["request_exact_match"] < thresholds.request_exact_match_min:
        gate_failures.append(
            f"request_exact_match {metrics['request_exact_match']:.2%} < {thresholds.request_exact_match_min:.2%}"
        )
    if metrics["action_accuracy"] < thresholds.action_accuracy_min:
        gate_failures.append(f"action_accuracy {metrics['action_accuracy']:.2%} < {thresholds.action_accuracy_min:.2%}")
    if metrics["ask_missing_recall"] < thresholds.ask_missing_recall_min:
        gate_failures.append(
            f"ask_missing_recall {metrics['ask_missing_recall']:.2%} < {thresholds.ask_missing_recall_min:.2%}"
        )
    if thresholds.safety_zero_fail and not metrics["safety_zero_fail"]:
        gate_failures.append(f"safety_zero_fail vi phạm ({safety_failures} ca thất bại)")
    if metrics["kwh_from_code"] < thresholds.kwh_from_code_min:
        gate_failures.append(f"kwh_from_code {metrics['kwh_from_code']:.2%} < {thresholds.kwh_from_code_min:.2%}")

    print(f"Eval Agent Online ({settings.llm_provider}) — {len(cases)} câu:")
    for k, v in metrics.items():
        val_str = f"{v:.2%}" if isinstance(v, float) else str(v)
        print(f"  {k:<22} {val_str}")

    if out is not None:
        out.mkdir(parents=True, exist_ok=True)
        summary = {
            "provider": settings.llm_provider,
            "dataset": dataset.name,
            "cases": len(cases),
            "metrics": metrics,
            "thresholds": thresholds.model_dump(),
            "passed": not gate_failures,
            "gate_failures": gate_failures,
            "records": records,
        }
        (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        md_lines = [
            f"# Agent F1 Evaluation Report (`{settings.llm_provider}`)",
            "",
            f"- **Dataset**: `{dataset.name}` ({len(cases)} cases)",
            f"- **Status**: {'PASS' if not gate_failures else 'FAIL'}",
            "",
            "| Metric | Value | Threshold |",
            "|---|---|---|",
            f"| `field_accuracy` | {metrics['field_accuracy']:.2%} | {thresholds.field_accuracy_min:.2%} |",
            f"| `request_exact_match` | {metrics['request_exact_match']:.2%} | {thresholds.request_exact_match_min:.2%} |",
            f"| `action_accuracy` | {metrics['action_accuracy']:.2%} | {thresholds.action_accuracy_min:.2%} |",
            f"| `ask_missing_recall` | {metrics['ask_missing_recall']:.2%} | {thresholds.ask_missing_recall_min:.2%} |",
            f"| `safety_zero_fail` | {metrics['safety_zero_fail']} | {thresholds.safety_zero_fail} |",
            f"| `kwh_from_code` | {metrics['kwh_from_code']:.2%} | {thresholds.kwh_from_code_min:.2%} |",
        ]
        (out / "report.md").write_text("\n".join(md_lines) + "\n", encoding="utf-8")
        print(f"==> Đã ghi {out / 'summary.json'} và {out / 'report.md'}")

    if gate_failures:
        print("\nKHÔNG ĐẠT NGƯỠNG:", file=sys.stderr)
        for gf in gate_failures:
            print(f"  - {gf}", file=sys.stderr)
        return 1
    print("OK — Agent đạt toàn bộ ngưỡng PRD §8.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Đánh giá Agent F1 trên bộ câu yêu cầu sạc có nhãn (PRD §8)")
    parser.add_argument("--dataset", type=Path, default=DATASET_DEFAULT)
    parser.add_argument("--offline", action="store_true", help="Chỉ kiểm dataset + ngưỡng, không gọi LLM (CI)")
    parser.add_argument("--out", type=Path, default=None, help="Thư mục ghi kết quả (mặc định: không ghi file)")
    parser.add_argument(
        "--delay",
        type=float,
        default=0.0,
        help="Số giây nghỉ giữa các câu khi chạy online (hữu ích cho API giới hạn 5–15 RPM như Gemini Free Tier)",
    )
    args = parser.parse_args(argv)
    if args.offline:
        return run_offline(args.dataset, args.out)
    try:
        return run_online(args.dataset, args.out, delay_seconds=args.delay)
    except NotImplementedError as exc:
        print(f"Chưa chạy được eval Agent — phần còn thiếu: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):  # console Windows (cp1258) không in được tiếng Việt có dấu
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
