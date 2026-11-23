"""Run ChargePilot's EV2Gym-based hybrid baseline and export an offline replay."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import sys
from datetime import UTC, datetime
from importlib.metadata import distribution
from pathlib import Path
from shutil import rmtree
from tempfile import mkdtemp
from uuid import uuid4

if __package__:
    from .src.algorithms import resolve_algorithms
    from .src.engine.hybrid import HybridSimulator
    from .src.safety.constraints import ConstraintViolationError
    from .src.scenario import Scenario
else:
    # Script mode (`python src/simulator/run.py`): put the repository root first so `src` is the repository package
    # and shared contracts in `src.models` resolve (ADR-019). Only this entrypoint bootstraps the path.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from src.simulator.src.algorithms import resolve_algorithms
    from src.simulator.src.engine.hybrid import HybridSimulator
    from src.simulator.src.safety.constraints import ConstraintViolationError
    from src.simulator.src.scenario import Scenario

ROOT = Path(__file__).resolve().parent
SCENARIOS = ROOT / "scenario"
VIEWER = ROOT.parents[1] / "frontend/public/chargepilot-replay.html"
ENGINE = "EV2Gym-based hybrid/DC extension"
VERSION = "1.2.0"


def resolve_scenario(value: str) -> Path:
    path = Path(value)
    if path.is_file():
        return path.resolve()
    candidate = SCENARIOS / (value if value.endswith(".json") else f"{value}.json")
    if not candidate.is_file():
        raise ValueError(f"Scenario not found: {value}. Use --list-scenarios.")
    return candidate


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def metadata_for(config, source_bytes, scenario, argv, algorithms):
    package = distribution("ev2gym")
    direct = json.loads(package.read_text("direct_url.json") or "{}")
    return {
        "engine": ENGINE,
        "version": VERSION,
        "ev2gym_version": package.version,
        "ev2gym_commit": direct.get("vcs_info", {}).get("commit_id"),
        "ev2gym_source_sha256": {
            name: hashlib.sha256(Path(package.locate_file(f"ev2gym/models/{name}.py")).read_bytes()).hexdigest()
            for name in ("ev", "ev_charger")
        },
        "native_ac": "EV.step AC with capacity rounding disabled",
        "native_dc": False,
        "dc_model": algorithms["dc_charging_model"]["name"],
        "python": platform.python_version(),
        "platform": platform.platform(),
        "seed": config.get("seed"),
        "randomness": "none",
        "scenario_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "timestep_minutes": scenario.timestep,
        "config": config,
        "command": sys.argv if argv is None else ["-m", "src.simulator.run", *argv],
        "time_convention": "Replay snapshots after boundary events; kW averages over the following interval. "
        "Power CSV uses interval start timestamps.",
        "power_convention": "Actual output is inferred from delivered battery kWh and configured charging efficiency.",
        "guard_tolerance": 1e-7,
        "policy": " / ".join(
            f"{zone}: {algorithms['dispatch'][zone]['name']} + {algorithms['optimizers'][zone]['name']}"
            for zone in ("AC", "DC")
        ),
        "algorithms": algorithms,
    }


def export(output: Path, result: dict, metadata: dict) -> Path:
    now = datetime.now(UTC)
    config_hash = metadata["scenario_sha256"][:10]
    run_id = f"{now:%Y%m%dT%H%M%S%fZ}-{config_hash}-{uuid4().hex[:8]}"
    output.mkdir(parents=True, exist_ok=True)
    run_dir = output / run_id
    # Publish only complete runs, even if artifact generation fails or processes run concurrently.
    staging = Path(mkdtemp(prefix=".run-", dir=output))
    try:
        frames = result["frames"]
        events = result["events"]
        trace = result["power_trace"]
        vehicles = result["vehicles"]
        metrics = {
            k: v
            for k, v in result.items()
            if k
            not in (
                "frames",
                "events",
                "power_trace",
                "vehicles",
                "scenario_id",
                "decision_trace",
                "decision_latency_ms",
            )
        }
        common = {
            "scenario_id": result["scenario_id"],
            "engine": ENGINE,
            "version": VERSION,
            "metadata": {**metadata, "run_id": run_id},
        }
        report = {**common, **metrics, "vehicles": vehicles}
        replay = {**common, "schema_version": 1, "frames": frames, "events": events}
        write_json(staging / "report.json", report)
        write_json(staging / "events.json", events)
        write_json(staging / "replay.json", replay)
        if "decision_trace" in result:
            write_json(staging / "decision_trace.json", result["decision_trace"])
            write_json(staging / "decision_latency_ms.json", result["decision_latency_ms"])
        write_csv(
            staging / "power_trace.csv",
            trace,
            [
                "time",
                "minute",
                "duration_minutes",
                "ac_output_kw",
                "dc_output_kw",
                "grid_input_kw",
                "ac_queue",
                "dc_queue",
                "occupied_ports",
            ],
        )
        write_csv(
            staging / "vehicles.csv",
            vehicles,
            [
                "id",
                "zone",
                "state",
                "connector",
                "last_connector",
                "initial_soc",
                "soc",
                "target",
                "arrival",
                "departure",
                "charge_started",
                "completed_at",
                "departed_at",
                "waiting_minutes",
                "wait_censored",
                "delivered_battery_kwh",
                "delivered_grid_kwh",
            ],
        )
        # Escape markup-sensitive characters before embedding data in a script element.
        embedded = json.dumps(replay, ensure_ascii=False, allow_nan=False).replace("<", "\\u003c")
        template = VIEWER.read_text(encoding="utf-8")
        html = template.replace('id="embedded-replay">null</script>', f'id="embedded-replay">{embedded}</script>', 1)
        (staging / "viewer.html").write_text(html, encoding="utf-8")
        staging.rename(run_dir)
    finally:
        if staging.exists():
            rmtree(staging)
    return run_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", default="mvp1", help="Bundled name or JSON path (default: mvp1)")
    parser.add_argument("--list-scenarios", action="store_true")
    parser.add_argument("--output-dir", type=Path, help="Parent directory for timestamped runs")
    parser.add_argument("--algorithms", type=Path, help="JSON algorithm selection overriding the scenario's algorithms")
    parser.add_argument(
        "--decision-trace", action="store_true", help="Export decision facts and separate wall-clock latency"
    )
    args = parser.parse_args(argv)
    if args.list_scenarios:
        for source in sorted(SCENARIOS.glob("*.json")):
            print(source.stem)
        return 0
    try:
        source = resolve_scenario(args.scenario)
        source_bytes = source.read_bytes()
        config = json.loads(source_bytes)
        scenario = Scenario.parse(config)
        if args.algorithms is None:
            selection, selection_source = config.get("algorithms", {}), f"{source}#algorithms"
        else:
            selection = json.loads(args.algorithms.read_bytes())
            selection_source = str(args.algorithms.resolve())
        algorithms, algorithm_metadata = resolve_algorithms(selection, scenario, selection_source)
        simulator = HybridSimulator(scenario, algorithms=algorithms, record_decisions=args.decision_trace)
        try:
            result = simulator.run()
        except ConstraintViolationError as exc:
            diagnostic = {
                "status": "constraint_failure",
                "scenario_id": scenario.id,
                "minute": simulator.now,
                **simulator.constraint_metrics(),
                "error": str(exc),
            }
            parser.exit(2, json.dumps(diagnostic) + "\n")
        run_dir = export(
            args.output_dir or ROOT / "outputs" / source.stem,
            result,
            metadata_for(config, source_bytes, scenario, argv, algorithm_metadata),
        )
    except (ValueError, KeyError, TypeError, OSError) as exc:
        parser.exit(2, f"Simulator error: {exc}\n")
    print(f"{result['scenario_id']} | {ENGINE}, EV2Gym {distribution('ev2gym').version}")
    first = result["frames"][0]
    print(
        f"{first['time']}: {sum(v is not None for v in first['ports'].values())} connected, "
        f"{len(first['queues']['AC'])} AC / {len(first['queues']['DC'])} DC waiting"
    )
    print(
        f"On time: {result['completed_on_time']}/{result['requests']} | "
        f"mean wait (started only): {result['mean_wait_minutes_started_only']} min | "
        f"peak grid: {result['peak_grid_input_kw']} kW"
    )
    print(f"Report: {run_dir / 'report.json'}\n2D replay: {run_dir / 'viewer.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
