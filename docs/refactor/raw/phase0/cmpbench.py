"""So hai output JSON của simulator (report / benchmark), bỏ đúng các trường THỜI GIAN TƯỜNG, và FAIL khi lệch.

Dùng: python cmpbench.py <baseline.json> <candidate.json> <label>
Exit 0 chỉ khi mọi khác biệt còn lại nằm trong ALLOWED (metadata của lần chạy). Exit 1 nếu lệch ở bất cứ chỗ nào khác.

Bản trước (Phase 0/1, đã thay 2026-11-23) bỏ qua mọi khoá chứa "solver", "path", "created"… nên đã bỏ sót
`rejected_solver_plan_count` (KPI) và `algorithm_metadata/*/solver` (cấu hình), và luôn trả exit 0.
"""

import json
import re
import sys

# Chỉ trường đo thời gian tường / môi trường máy: tên khoá khớp TOÀN BỘ một trong các mẫu này.
TIMING_KEY = re.compile(
    r"^(decision_latency_ms|solver_latency_ms|solver_latency_by_zone_ms|latency_p95_target_ms|solver_ms|"
    r"decision_ms|software|platform|python)$"
)
# Khác biệt được phép: định danh lần chạy và đường dẫn tuyệt đối của file cấu hình.
ALLOWED = re.compile(r"^/metadata/(run_id|command|algorithms/.*/config_source)$")


def walk(a, b, p, diffs):
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if TIMING_KEY.match(str(k)):
                continue
            if k not in a or k not in b:
                diffs.append((p + "/" + str(k), "missing", k in a, k in b))
                continue
            walk(a[k], b[k], p + "/" + str(k), diffs)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            diffs.append((p, "len", len(a), len(b)))
            return
        for i, (x, y) in enumerate(zip(a, b, strict=True)):
            walk(x, y, f"{p}[{i}]", diffs)
    elif isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        if abs(a - b) > 1e-9 * max(1, abs(a)):
            diffs.append((p, "num", a, b))
    elif a != b:
        diffs.append((p, "val", str(a)[:60], str(b)[:60]))


def main() -> int:
    a = json.load(open(sys.argv[1], encoding="utf-8"))
    b = json.load(open(sys.argv[2], encoding="utf-8"))
    diffs = []
    walk(a, b, "", diffs)
    unexpected = [d for d in diffs if not ALLOWED.match(d[0])]
    status = "OK" if not unexpected else "FAIL"
    print(f"{sys.argv[3]}: {status} — {len(unexpected)} unexpected, {len(diffs) - len(unexpected)} allowed metadata")
    for d in unexpected[:20]:
        print("   UNEXPECTED", d)
    for d in [d for d in diffs if ALLOWED.match(d[0])][:10]:
        print("   allowed   ", d[0])
    return 1 if unexpected else 0


if __name__ == "__main__":
    raise SystemExit(main())
