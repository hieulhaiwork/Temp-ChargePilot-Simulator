import collections
import json
import sys

rows = json.load(open(sys.argv[1]))


def layer(path):
    p = path.split("/")
    if p[0] == "src":
        if len(p) > 2 and p[1] == "simulator":
            if p[2] == "src":
                return "simulator.src(core)"
            if p[2] == "tests":
                return "simulator.tests"
            return "simulator." + p[2].removesuffix(".py")
        return p[1].removesuffix(".py")
    return p[0]


def tlayer(m):
    p = m.split(".")
    if p[0] != "src":
        return None
    if len(p) > 2 and p[1] == "simulator":
        return "simulator.src(core)" if p[2] == "src" else "simulator." + p[2]
    return p[1] if len(p) > 1 else "src"


edges = collections.Counter()
lazy = collections.Counter()
for f, m, _lineno, lz, _names in rows:
    t = tlayer(m)
    if not t:
        continue
    s = layer(f)
    if s == t:
        continue
    edges[(s, t)] += 1
    if lz:
        lazy[(s, t)] += 1
for (s, t), n in sorted(edges.items()):
    print(f"{s:28} -> {t:24} {n:4}  lazy={lazy[(s, t)]}")
