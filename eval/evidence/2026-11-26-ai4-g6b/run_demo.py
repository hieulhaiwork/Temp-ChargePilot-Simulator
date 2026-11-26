"""Serve unified chat with seeded SQLite, a scripted model and real advisory engines."""

import argparse
import asyncio
import os
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RESIDENT_WHY = "Vì sao xe tôi đang chờ?"
RESIDENT_WHAT_IF = "Xem xe tôi xoay xở ra sao với mục tiêu 75%."
RESIDENT_COMPOUND = (
    "Tôi cần đi sau 70 phút, thử mức từ 65% đến 75%. "
    "Vì sao xe tôi đang chờ và có phương án nào tốt hơn không? "
    "Tôi đồng ý giảm mục tiêu. Tôi đồng ý mất cam kết gốc. Giữ nguyên hoặc rút ngắn hạn."
)
OPERATOR_WHY = "Vì sao các xe bị trễ?"
OPERATOR_WHAT_IF = "Xem bãi xoay xở thế nào với nguồn 50 kW, dùng bản sao mô phỏng."
OPERATOR_COMPOUND = (
    "Vì sao các xe bị trễ và cần nguồn điện bao nhiêu để đáp ứng các cam kết? "
    "Thử 22 đến 106 kW, giữ các xe AC đúng hạn."
)


async def demo(port: int, ranked: bool) -> None:
    import uvicorn
    from alembic import command
    from alembic.config import Config

    from src.api import routes
    from src.config import get_settings
    from src.llm_chat.graph import build_graph
    from src.llm_chat.schemas import AgentDecision
    from src.main import app
    from src.models.control import Role
    from src.models.identity import UserRecord
    from src.services import auth, repository, runtime
    from tests.test_api.test_copilot import PASSWORD, seed_demo
    from tests.test_api.test_unified_copilot import OPERATOR_WHY as OPERATOR_WHY_ARGS
    from tests.test_api.test_unified_copilot import RESIDENT_WHY as RESIDENT_WHY_ARGS
    from tests.test_api.test_unified_copilot import decision
    from tests.test_services.test_recommendation import _max_at, _site
    from tests.test_services.test_recommendation_hybrid import _hybrid_runtime

    db = Config(str(ROOT / "alembic.ini"))
    db.set_main_option("script_location", str(ROOT / "migrations"))
    db.set_main_option("sqlalchemy.url", get_settings().database_url)
    command.upgrade(db, "head")
    if ranked:
        rt = _hybrid_runtime(
            "M3b",
            (
                ("a", "DC", 30, 50, 27),
                ("dc-rival", "DC", 35, 54, 27),
                ("ac-a", "AC", 30, 31, 22),
                ("ac-b", "AC", 40, 41, 22),
            ),
        )
        repository.upsert_user(
            UserRecord(
                user_id="operator",
                email="operator@g6a.example",
                role=Role.OPERATOR,
                password_hash=auth.hash_password(PASSWORD),
                display_name="operator",
                created_at=rt.clock(),
            )
        )
        own = rt.store.get_booking("a")
        assert own
    else:
        rt, own, _ = await seed_demo()
    runtime._live = rt
    resident_goal = _max_at(
        rt,
        70,
        booking_id=own.booking_id,
        low=65,
        high=75,
        allow_lower_target=True,
        allow_subject_original_sla_regression=True,
    )
    resident_goal["deadline"] = (rt.simulator.now + timedelta(minutes=70)).isoformat()
    cases = {
        RESIDENT_WHY: (decision("copilot_why", RESIDENT_WHY_ARGS),),
        RESIDENT_WHAT_IF: (
            decision(
                "copilot_what_if",
                {"kind": "what_if", "change": {"op": "revise_vehicle", "target_soc": 75}},
            ),
        ),
        RESIDENT_COMPOUND: (
            decision("copilot_why", RESIDENT_WHY_ARGS, done=False),
            decision("copilot_how_to", {"goal": resident_goal}),
        ),
        OPERATOR_WHY: (decision("copilot_why", OPERATOR_WHY_ARGS),),
        OPERATOR_WHAT_IF: (
            decision(
                "copilot_what_if",
                {"kind": "what_if", "change": {"op": "site_limit", "grid_input_kw": 50}},
            ),
        ),
        OPERATOR_COMPOUND: (
            decision("copilot_why", OPERATOR_WHY_ARGS, done=False),
            decision(
                "copilot_how_to",
                {"goal": _site(22, 106, min_original_on_time_rate=1.0), "horizon_minutes": 120},
            ),
        ),
    }

    async def scripted_model(state):
        options = cases.get(state["query"])
        index = state.get("iteration_count", 0)
        if options and index < len(options):
            return AgentDecision.model_validate(options[index])
        return AgentDecision(thought="fixture case selection", action="clarify", clarify_field="intent")

    routes.agent = build_graph(reason_fn=scripted_model)
    await uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port)).serve()


def main() -> None:
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("--port", type=int, default=8019)
    args.add_argument("--ranked", action="store_true", help="Use the approved M3b ranked-options workload.")
    options = args.parse_args()
    sys.path.insert(0, str(ROOT))
    os.chdir(ROOT)
    os.environ.pop("TEST_DATABASE_URL", None)
    import tests  # noqa: F401  # Force a new temporary SQLite before application imports.

    os.environ.update(
        LLM_PROVIDER="mock",
        CONTROL_LOOP_ENABLED="false",
        AGENT_PLAYGROUND="false",
        SEED_USERS_JSON="",
        DECISION_TRACE_DIR="",
        APP_ENV="development",
    )
    asyncio.run(demo(options.port, options.ranked))


if __name__ == "__main__":
    main()
