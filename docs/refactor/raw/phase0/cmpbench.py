import json
import re
import sys

TIMING = re.compile(
    r"(_ms|latency|decision_p\d+|solver|elapsed|wall|duration_s|software|platform|python|timestamp|created|output_dir|path)",
    re.I,
)


def walk(a, b, p, diffs):
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if TIMING.search(str(k)):
                continue
            if k not in a or k not in b:
                diffs.append((p + "/" + str(k), "missing", k in a, k in b))
                continue
            walk(a[k], b[k], p + "/" + str(k), diffs)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            diffs.append((p, "len", len(a), len(b)))
            return
        for i, (x, y) in enumerate(zip(a, b)):
            walk(x, y, f"{p}[{i}]", diffs)
    elif isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        if abs(a - b) > 1e-9 * max(1, abs(a)):
            diffs.append((p, "num", a, b))
    elif a != b:
        diffs.append((p, "val", str(a)[:60], str(b)[:60]))


a = json.load(open(sys.argv[1], encoding="utf-8"))
b = json.load(open(sys.argv[2], encoding="utf-8"))
d = []
walk(a, b, "", d)
print(f"{sys.argv[3]}: {len(d)} non-timing differences")
for x in d[:15]:
    print("  ", x)
