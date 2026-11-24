"""Resolved experiment configuration — provenance của mỗi run (Final Acceptance §3.2).

Vì sao tồn tại: một con số benchmark / admission chỉ so được với con số khác khi biết ĐÚNG cấu hình đã chạy: policy id +
version, từng thành phần (dispatch / optimizer / coordinator / Physical Guard) với version + tham số ĐẦY ĐỦ sau mặc
định, DC charging model, `TimeConfig`, cấu hình trạm và biểu giá. Ở đây dựng bản tường minh đó TỪ runtime thật (metadata
mà `resolve_algorithms` trả cho scheduler, không chép tay) và băm thành `fingerprint` ổn định: cùng fingerprint ⇒ cùng
cấu hình đã resolve.

Dùng chung cho live, benchmark (`simulation_service`) và admission (`fork_runtime`) — mỗi đường gọi `resolve_experiment`
trên runtime của nó, nên so fingerprint là kiểm config parity.
"""

import hashlib
import json

from src.models.simulation import ResolvedComponent, ResolvedExperiment

# Khoá thành phần trong `ResolvedExperiment.components` ↔ đường trong metadata của `resolve_algorithms`.
COMPONENTS = (
    ("dispatch.AC", ("dispatch", "AC")),
    ("dispatch.DC", ("dispatch", "DC")),
    ("optimizers.AC", ("optimizers", "AC")),
    ("optimizers.DC", ("optimizers", "DC")),
    ("coordinator", ("coordinator",)),
    ("physical_guard", ("physical_guard",)),
)


def canonical_sha256(value) -> str:
    """sha256 của JSON chuẩn hoá (khoá sắp xếp, không khoảng trắng, UTF-8) — ổn định giữa các lần chạy / máy."""
    text = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _component(meta: dict) -> ResolvedComponent:
    return ResolvedComponent(
        name=str(meta["name"]),
        version=str(meta["version"]),
        implementation=meta.get("implementation"),
        parameters=dict(meta.get("parameters") or {}),
    )


def _lookup(metadata: dict, path: tuple[str, ...]) -> dict:
    node = metadata
    for key in path:
        node = node[key]
    return node


def resolve_experiment(rt) -> ResolvedExperiment:
    """Cấu hình đã resolve của runtime `rt` (live / benchmark / fork admission). Lỗi rõ nếu scheduler thiếu metadata."""
    scheduler = rt.scheduler
    metadata = getattr(scheduler, "metadata", None)
    if not metadata and callable(getattr(scheduler, "algorithms", None)):
        scheduler.algorithms()  # metadata dựng lười cùng algorithms
        metadata = scheduler.metadata
    if not metadata:
        raise ValueError(f"Scheduler {type(scheduler).__name__} không có metadata thành phần — không resolve được")
    station = rt.simulator
    time_config = station.time.as_dict() if getattr(station, "time", None) is not None else {}
    draft = ResolvedExperiment(
        policy_id=str(scheduler.policy_id),
        policy_version=str(scheduler.policy_version),
        components={key: _component(_lookup(metadata, path)) for key, path in COMPONENTS},
        dc_charging_model=_component(metadata["dc_charging_model"]),
        parameters={k: dict(v) for k, v in (getattr(scheduler, "parameters", None) or {}).items()},
        time_config=time_config,
        station_config_sha256=canonical_sha256(rt.config.model_dump(mode="json")),
        tariff_sha256=canonical_sha256(rt.tariff.model_dump(mode="json")) if rt.tariff is not None else None,
        fingerprint="",
    )
    # Băm dạng JSON (tuple → list, số giữ nguyên) ⇒ cùng giá trị cho bản dựng lại từ file JSON.
    payload = draft.model_dump(mode="json", exclude={"fingerprint"})
    return draft.model_copy(update={"fingerprint": canonical_sha256(payload)})


def try_resolve_experiment(rt) -> ResolvedExperiment | None:
    """Như `resolve_experiment` nhưng trả None cho scheduler không phải policy registry (scheduler giả trong test)."""
    if not hasattr(rt.scheduler, "policy_id"):
        return None
    try:
        return resolve_experiment(rt)
    except (KeyError, ValueError, TypeError):
        return None


__all__ = ["canonical_sha256", "resolve_experiment", "try_resolve_experiment"]
