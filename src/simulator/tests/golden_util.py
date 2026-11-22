"""Canonical hashes of simulator outputs for regression (golden) checks."""

import hashlib
import json

PARTS = ("summary", "vehicles", "events", "power_trace", "frames")


def canonical_parts(result: dict) -> dict[str, str]:
    summary = {
        k: v
        for k, v in result.items()
        if k not in ("frames", "events", "power_trace", "vehicles", "decision_trace", "decision_latency_ms")
    }
    payload = {
        "summary": summary,
        "vehicles": result["vehicles"],
        "events": result["events"],
        "power_trace": result["power_trace"],
        "frames": result["frames"],
    }
    return {
        part: hashlib.sha256(
            json.dumps(payload[part], sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
        ).hexdigest()
        for part in PARTS
    }
