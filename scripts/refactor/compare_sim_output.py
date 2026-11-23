"""Cổng kiểm KPI: so hai output JSON của simulator (report / benchmark) và FAIL khi lệch (ADR-019).

Dùng:
    python scripts/refactor/compare_sim_output.py <baseline.json> <candidate.json> <label> [--module-map OLD=NEW ...]

- Bỏ qua ĐÚNG các trường thời gian tường / máy đo (TIMING_KEY, khớp toàn bộ tên khoá).
- Cho phép khác ở metadata của lần chạy (ALLOWED: run_id, command, đường dẫn file cấu hình).
- Trường `.../implementation` (đường dẫn Python của thuật toán) chỉ được khác khi `--module-map` biến đúng giá trị cũ
  thành giá trị mới (module được di chuyển có khai báo). Mọi khác biệt khác → exit 1.
"""

import argparse
import json
import re
import sys

TIMING_KEY = re.compile(
    r"^(decision_latency_ms|solver_latency_ms|solver_latency_by_zone_ms|latency_p95_target_ms|solver_ms|"
    r"decision_ms|software|platform|python)$"
)
ALLOWED = re.compile(r"^/metadata/(run_id|command|algorithms/.*/config_source)$")
IMPLEMENTATION = re.compile(r"/implementation$")


def walk(a, b, path: str, diffs: list) -> None:
    if isinstance(a, dict) and isinstance(b, dict):
        for key in sorted(set(a) | set(b)):
            if TIMING_KEY.match(str(key)):
                continue
            if key not in a or key not in b:
                diffs.append((f"{path}/{key}", "missing", key in a, key in b))
                continue
            walk(a[key], b[key], f"{path}/{key}", diffs)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            diffs.append((path, "len", len(a), len(b)))
            return
        for index, (x, y) in enumerate(zip(a, b, strict=True)):
            walk(x, y, f"{path}[{index}]", diffs)
    elif isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        if abs(a - b) > 1e-9 * max(1, abs(a)):
            diffs.append((path, "num", a, b))
    elif a != b:
        diffs.append((path, "val", a, b))


def remap(value: str, module_map: dict[str, str]) -> str:
    for old, new in module_map.items():
        if value == old or value.startswith(old + "."):
            return new + value[len(old) :]
    return value


def classify(diffs: list, module_map: dict[str, str]) -> tuple[list, list]:
    allowed, unexpected = [], []
    for diff in diffs:
        path, kind, old, new = diff
        if ALLOWED.match(path):
            allowed.append(diff)
        elif IMPLEMENTATION.search(path) and kind == "val" and isinstance(old, str) and remap(old, module_map) == new:
            allowed.append(diff)
        else:
            unexpected.append(diff)
    return allowed, unexpected


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("baseline")
    parser.add_argument("candidate")
    parser.add_argument("label")
    parser.add_argument("--module-map", action="append", default=[], help="OLD.module=NEW.module")
    args = parser.parse_args(argv)
    module_map = dict(item.split("=", 1) for item in args.module_map)
    with open(args.baseline, encoding="utf-8") as fa, open(args.candidate, encoding="utf-8") as fb:
        a, b = json.load(fa), json.load(fb)
    diffs: list = []
    walk(a, b, "", diffs)
    allowed, unexpected = classify(diffs, module_map)
    status = "OK" if not unexpected else "FAIL"
    print(f"{args.label}: {status} - {len(unexpected)} unexpected, {len(allowed)} allowed")
    for diff in unexpected[:20]:
        print("   UNEXPECTED", diff[0], diff[1], str(diff[2])[:80], str(diff[3])[:80])
    kinds = sorted({re.sub(r"\[\d+\]", "[]", d[0]) for d in allowed})
    for path in kinds[:30]:
        print("   allowed   ", path)
    return 1 if unexpected else 0


if __name__ == "__main__":
    raise SystemExit(main())
