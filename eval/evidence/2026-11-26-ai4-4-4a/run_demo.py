"""Run the reproducible G6A demo with temporary SQLite and synthetic bookings."""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


async def demo(serve: bool, port: int) -> dict | None:
    from alembic import command
    from alembic.config import Config
    from httpx import ASGITransport, AsyncClient

    from src.config import get_settings
    from src.main import app
    from src.services import runtime
    from tests.test_api.test_copilot import HOW_TO, OUTAGE, PREFIX, SOC, WHY, login, seed_demo, wait_job

    db = Config(str(ROOT / "alembic.ini"))
    db.set_main_option("script_location", str(ROOT / "migrations"))
    db.set_main_option("sqlalchemy.url", get_settings().database_url)
    command.upgrade(db, "head")
    rt, own, dc = await seed_demo()
    runtime._live = rt
    connector = next(row.connector_id for row in rt.simulator.state().connectors if row.booking_id == dc.booking_id)
    if serve:
        import uvicorn

        print(f"Fixture initialized. The occupied DC connector is {connector}.", flush=True)
        await uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port)).serve()
        return None
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://fixture") as client:
            resident, operator = await login(client, own.resident_id), await login(client, "operator")

            async def request(question, headers, *, selected_connector_id=None):
                response = await client.post(
                    f"{PREFIX}/query",
                    headers=headers,
                    json={"message": question, "selected_connector_id": selected_connector_id},
                )
                response.raise_for_status()
                reply = response.json()
                if response.status_code == 202:
                    reply["job"] = await wait_job(client, headers, reply["job"]["job_id"])
                    assert reply["job"]["status"] == "succeeded", reply
                return {"question": question, "http": response.status_code, **reply}

            why = await request(WHY, resident)
            soc = await request(SOC, resident)
            outage = await request(OUTAGE, operator, selected_connector_id=connector)
            deferred = await request(HOW_TO, operator)
            assert why["kind"] == "why" and why["result"]["reasons"]
            assert soc["job"]["result"]["result"]["patch"]["target_soc"] == 75
            assert outage["job"]["result"]["result"]["patch"]["duration_minutes"] == 30
            assert deferred["code"] == "feature_not_available"
            site_request = await client.post(
                f"{PREFIX}/what-if",
                headers=operator,
                json={"patch": {"op": "site_limit", "grid_input_kw": 15}, "horizon_minutes": 8},
            )
            assert site_request.status_code == 202
            site = await wait_job(client, operator, site_request.json()["job"]["job_id"])
            assert site["status"] == "succeeded", site
            return {
                "provider": "deterministic fallback (LLM_PROVIDER=mock)",
                "station_as_of": rt.simulator.now.isoformat(),
                "resident_why": why,
                "resident_soc": soc,
                "operator_outage": outage,
                "operator_site_limit": site,
                "deferred_how_to": deferred,
            }


def main() -> None:
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("--serve", action="store_true", help="Serve fixture-backed API on loopback for the web UI.")
    args.add_argument("--port", type=int, default=8000)
    args.add_argument("--out", type=Path)
    options = args.parse_args()
    sys.path.insert(0, str(ROOT))
    os.chdir(ROOT)
    os.environ.pop("TEST_DATABASE_URL", None)
    import tests  # noqa: F401  # Creates a dedicated temporary SQLite database before application imports.

    os.environ.update(
        {
            "LLM_PROVIDER": "mock",
            "CONTROL_LOOP_ENABLED": "false",
            "AGENT_PLAYGROUND": "false",
            "SEED_USERS_JSON": "",
            "DECISION_TRACE_DIR": "",
        }
    )
    result = asyncio.run(demo(options.serve, options.port))
    if result is not None:
        output = json.dumps(result, ensure_ascii=False, indent=2)
        if options.out is not None:
            options.out.write_text(output + "\n", encoding="utf-8")
        else:
            print(output)


if __name__ == "__main__":
    main()
