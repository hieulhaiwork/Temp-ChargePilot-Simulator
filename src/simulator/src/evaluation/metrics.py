"""Report KPIs derived from final vehicle rows and the power trace."""

from math import ceil

from ..scenario import Scenario


def summarize(
    scenario: Scenario,
    now: int,
    rows: list[dict],
    trace: list[dict],
    constraint_metrics: dict[str, int],
) -> dict:
    completed = sum(r["completed_at"] is not None and r["completed_at"] <= r["departure"] for r in rows)
    waits = sorted(r["waiting_minutes"] for r in rows if r["charge_started"] is not None)
    capacity_kwh = {vehicle.id: vehicle.battery_kwh for vehicle in scenario.vehicles}
    return {
        "requests": len(rows),
        "completed_on_time": completed,
        "served_sessions": len(waits),
        "satisfied_demand_rate": round(completed / len(rows), 4) if rows else None,
        "mean_wait_minutes_started_only": round(sum(waits) / len(waits), 2) if waits else None,
        "p95_wait_minutes_started_only": waits[ceil(0.95 * len(waits)) - 1] if waits else None,
        "missed_deadline_sessions": sum(r["completed_at"] is None and r["departure"] <= now for r in rows),
        "pending_target_sessions": sum(r["completed_at"] is None and r["departure"] > now for r in rows),
        "unstarted_sessions": len(rows) - len(waits),
        "waited_then_left_without_charging": sum(
            r["charge_started"] is None and r["departed_at"] is not None for r in rows
        ),
        "queue_wait_for_all_arrivals": [
            {"vehicle_id": r["id"], "minutes": r["waiting_minutes"], "censored": r["wait_censored"]}
            for r in rows
            if r["waiting_minutes"] is not None
        ],
        **constraint_metrics,
        "constraint_violation_count": constraint_metrics["applied_constraint_violation_count"],  # Legacy report key.
        "total_grid_energy_kwh": round(sum(r["delivered_grid_kwh"] for r in rows), 3),
        "total_battery_energy_kwh": round(sum(r["delivered_battery_kwh"] for r in rows), 3),
        "remaining_demand_kwh": round(
            sum(max(0.0, row["target"] - row["soc"]) * capacity_kwh[row["id"]] for row in rows),
            3,
        ),
        "peak_grid_input_kw": round(max(row["grid_input_kw"] for row in trace), 3),
    }
