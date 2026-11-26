import asyncio
from datetime import timedelta

from src.models.control import Role
from src.services import catalog
from src.services.copilot import capture_atomic_snapshot, run_recommendation
from src.services.runtime import build_sim_runtime, visit_of
from tests.factories import NOW, booking
from tests.test_services.test_recommendation import _actor, _earliest, _max_at, _site

def setup(policy, cap=106):
    cfg = catalog.load_station_config().model_copy(update={"grid_input_limit_kw": cap, "power_limit_kw": cap})
    return build_sim_runtime(catalog.load_scenario("hybrid_evening"), policy, cfg, catalog.load_tariff(), NOW)

def add(rt, name, soc, target, minute, zone):
    b = booking(name, now=rt.clock(), hours=minute / 60, zone=zone)
    b.request.soc_now = soc
    b.request.soc_target = target
    stored = 60.13 * (target - soc) / 100
    b.energy = b.energy.model_copy(update={"soc_now": soc, "soc_target": target, "battery_energy_kwh": stored,
                                         "grid_energy_kwh": stored / .98, "efficiency": .98})
    rt.store.save_booking(b)
    rt.simulator.upsert_vehicle(visit_of(b, rt.clock()))

def brief(result):
    def rel(dt):
        return None if dt is None else round((dt-result.known_at).total_seconds()/60, 3)
    def ev(e):
        if e is None: return None
        if e.original_sla:
            return [(b.booking_id,b.original.met_deadline,rel(b.original.target_reached_at),
                     round(b.original.remaining_battery_kwh,4)) for b in e.booking_sla]
        return (e.subject_original.met_deadline, rel(e.subject_original.target_reached_at), rel(e.subject_release_at),
                None if e.subject_revised is None else (e.subject_revised.met_deadline,rel(e.subject_revised.target_reached_at)),
                None if e.subject_soc_at_deadline_pct is None else round(e.subject_soc_at_deadline_pct, 6),
                (e.branch_status, e.hard_violations, e.blocked_commands, e.rejected_allocations))
    return (result.search_status, result.baseline_issue, ev(result.baseline),
            [(rel(c.value) if not isinstance(c.value,float) else round(c.value,3), str(c.feasibility), c.reason, ev(c.evidence)) for c in result.candidates],
            [rel(c.value) if not isinstance(c.value,float) else round(c.value,3) for c in result.options])

async def main():
    for policy in ("M3a","M3b"):
        for cap, subject, rival in (
            (65, (66, 83, 38), (60, 90, 34)),
            (65, (30, 65, 48), (30, 72, 32)),
            (80, (50, 80, 50), (45, 80, 29)),
            (90, (65, 80, 35), (60, 82, 25)),
            (106, (65, 80, 35), (60, 82, 25)),
            (55, (30, 59, 55), (30, 65, 30)),
        ):
            rt = setup(policy, cap)
            add(rt,"a",*subject,"DC")
            add(rt,"dc-rival",*rival,"DC")
            add(rt,"ac-a",30,35,36,"AC")
            add(rt,"ac-b",40,42,28,"AC")
            snap = await capture_atomic_snapshot(rt, horizon_minutes=60)
            earliest = _earliest(rt, 18, min(42,subject[2]), target_soc=subject[1], allow_subject_original_sla_regression=True)
            res = await run_recommendation(snap, _actor(rt), earliest)
            print("earliest",policy,cap,subject,rival,brief(res),flush=True)
            if subject[0] >= 65:
                goal = _max_at(rt, 18, low=70, high=90, allow_lower_target=True, allow_subject_original_sla_regression=True)
                res = await run_recommendation(snap, _actor(rt), goal)
                print("max",policy,cap,subject,rival,brief(res),flush=True)

        for target, deadline, ac_target, ac_deadline in ((52,28,35,36),(57,32,33,25),(65,28,33,29),(55,30,35,36),(50,27,31,22)):
            rt=setup(policy,75)
            add(rt,"a",30,target,deadline,"DC")
            add(rt,"dc-rival",35,target+4,deadline,"DC")
            add(rt,"ac-a",30,ac_target,ac_deadline,"AC")
            add(rt,"ac-b",40,ac_target+10,ac_deadline,"AC")
            snap=await capture_atomic_snapshot(rt,horizon_minutes=45)
            res=await run_recommendation(snap,_actor(rt,role=Role.OPERATOR),
                                         _site(22,106, hypothetical_infrastructure=True, min_original_on_time_rate=.75))
            print("site",policy,target,deadline,ac_target,ac_deadline,brief(res),flush=True)

asyncio.run(main())
