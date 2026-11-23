"""Hash nội dung (sha256 file) + hash AST đã bỏ docstring, cho mỗi file Python. Phase 2 dùng hash AST để chứng minh
'chỉ di chuyển': sau khi đổi import, so hash AST của từng hàm/lớp (không tính câu import)."""

import ast
import hashlib
import pathlib
import sys


def strip(tree):
    for n in ast.walk(tree):
        if (
            isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef))
            and n.body
            and isinstance(n.body[0], ast.Expr)
            and isinstance(getattr(n.body[0], "value", None), ast.Constant)
            and isinstance(n.body[0].value.value, str)
        ):
            n.body = n.body[1:] or [ast.Pass()]
    return tree


print("# path | sha256(file)[:16] | sha256(ast, no docstrings)[:16] | top-level defs: name=sha256(ast)[:12]")
for root in sys.argv[1:]:
    r = pathlib.Path(root)
    for p in [r] if r.is_file() else sorted(r.rglob("*.py")):
        if "__pycache__" in p.parts:
            continue
        raw = p.read_bytes()
        tree = strip(ast.parse(raw.decode("utf-8")))
        defs = [
            f"{n.name}={hashlib.sha256(ast.dump(n).encode()).hexdigest()[:12]}"
            for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef))
        ]
        body = [n for n in tree.body if not isinstance(n, (ast.Import, ast.ImportFrom))]
        print(
            f"{p.as_posix()} | {hashlib.sha256(raw).hexdigest()[:16]} | {hashlib.sha256(ast.dump(ast.Module(body=body, type_ignores=[])).encode()).hexdigest()[:16]} | {' '.join(defs)}"
        )
