"""Record whole-pair WHAT-IF wall time and repeatability on a small synthetic fixture."""

import asyncio
import json
import statistics
import sys
import time
from datetime import timedelta
from pathlib import Path

from src.models.charging import StrategyName
from src.models.control import Role
from src.models.copilot import ActorContext
from src.services import catalog
from src.services.copilot import capture_atomic_snapshot, run_what_if
from src.services.runtime import build_sim_runtime, visit_of
from tests.factories import NOW, booking


async def run(out: Path) -> None:
    config, tariff = catalog.load_station_config(), catalog.load_tariff()
    rt = build_sim_runtime(catalog.load_scenario("hybrid_evening"), StrategyName.SIM_B0, config, tariff, NOW)
    record = booking("demo-ac", now=rt.clock(), hours=0.5)
    rt.store.save_booking(record)
    rt.simulator.upsert_vehicle(visit_of(record, rt.clock()))
    snapshot = await capture_atomic_snapshot(rt, horizon_minutes=25)
    actor = ActorContext(actor_id="synthetic-operator", role=Role.OPERATOR, station_id=config.station_id)
    patches = {
        "target_soc": {"op": "revise_vehicle", "booking_id": record.booking_id, "target_soc": 21},
        "deadline": {
            "op": "revise_vehicle",
            "booking_id": record.booking_id,
            "deadline": rt.clock() + timedelta(minutes=18),
        },
        "site_limit": {"op": "site_limit", "grid_input_kw": 8},
        "outage": {"op": "outage", "connector_id": "AC-01-1", "duration_minutes": 4},
    }
    output = {}
    for label, patch in patches.items():
        samples = []
        signature = None
        result = None
        for _ in range(3):
            start = time.perf_counter()
            result = await run_what_if(snapshot, actor, patch)
            samples.append(round((time.perf_counter() - start) * 1000, 3))
            current = result.model_dump(exclude={"baseline": {"run_id"}, "patched": {"run_id"}}, mode="json")
            assert result.status == "completed" and result.applied is False
            assert signature is None or signature == current, label
            signature = current
        output[label] = {
            "elapsed_ms": samples,
            "median_ms": statistics.median(samples),
            "max_ms": max(samples),
            "paired_result": result.model_dump(mode="json"),
        }
        print(
            f"{label}: 3/3 repeated signatures, median={statistics.median(samples):.3f} ms, max={max(samples):.3f} ms"
        )
    out.write_text(json.dumps({"fixture": "B0 synthetic AC, 25 simulated minutes", "operations": output}, indent=2))


if __name__ == "__main__":
    asyncio.run(run(Path(sys.argv[1])))
