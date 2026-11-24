import ast
import json
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
rows = []
scan = ["src", "tests", "eval", "scripts", "migrations"]
for d in scan:
    for p in (root / d).rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except Exception as e:
            print("PARSEFAIL", p, e, file=sys.stderr)
            continue
        mod_lazy = set()
        for fn in ast.walk(tree):
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for n in ast.walk(fn):
                    if isinstance(n, (ast.Import, ast.ImportFrom)):
                        mod_lazy.add(id(n))
        for n in ast.walk(tree):
            if isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
                rows.append(
                    (p.relative_to(root).as_posix(), n.module, n.lineno, id(n) in mod_lazy, [a.name for a in n.names])
                )
            elif isinstance(n, ast.Import):
                for a in n.names:
                    rows.append((p.relative_to(root).as_posix(), a.name, n.lineno, id(n) in mod_lazy, []))
json.dump(rows, open(sys.argv[2], "w"), ensure_ascii=False)
print(len(rows))
