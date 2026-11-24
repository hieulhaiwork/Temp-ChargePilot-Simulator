"""In manifest hash cho file Python: dùng để chứng minh một lần refactor CHỈ di chuyển code (ADR-019).

Mỗi dòng: `path | sha256(file)[:16] | sha256(AST thân module, bỏ docstring + import)[:16] | name=hash ...`.
Hash từng định nghĩa top-level (hàm, lớp, và phép gán một tên như `DISPATCH = {...}`) tính trên AST đã bỏ docstring,
nên đổi import / docstring / format không làm đổi hash, còn đổi thân hàm, hằng số, tham số thì có.

Dùng: python scripts/refactor/ast_manifest.py <file-hoặc-thư-mục> ...
"""

import ast
import hashlib
import pathlib
import sys

DEF_TYPES = (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)


def strip_docstrings(tree: ast.AST) -> ast.AST:
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.Module, *DEF_TYPES))
            and node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(getattr(node.body[0], "value", None), ast.Constant)
            and isinstance(node.body[0].value.value, str)
        ):
            node.body = node.body[1:] or [ast.Pass()]
    return tree


def _digest(node: ast.AST, size: int) -> str:
    return hashlib.sha256(ast.dump(node).encode()).hexdigest()[:size]


def definitions(tree: ast.Module) -> list[tuple[str, str]]:
    """(tên, hash) của hàm / lớp / phép gán MỘT tên ở cấp module."""
    found = []
    for node in tree.body:
        if isinstance(node, DEF_TYPES):
            found.append((node.name, _digest(node, 12)))
        elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            found.append((node.targets[0].id, _digest(node.value, 12)))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
            found.append((node.target.id, _digest(node.value, 12)))
    return found


def manifest_lines(roots: list[str]) -> list[str]:
    lines = ["# path | sha256(file)[:16] | sha256(ast, no docstrings/imports)[:16] | top-level defs: name=sha256[:12]"]
    for root in roots:
        base = pathlib.Path(root)
        for path in [base] if base.is_file() else sorted(base.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            raw = path.read_bytes()
            tree = strip_docstrings(ast.parse(raw.decode("utf-8")))
            body = [n for n in tree.body if not isinstance(n, (ast.Import, ast.ImportFrom))]
            module_hash = _digest(ast.Module(body=body, type_ignores=[]), 16)
            defs = " ".join(f"{name}={digest}" for name, digest in definitions(tree))
            lines.append(f"{path.as_posix()} | {hashlib.sha256(raw).hexdigest()[:16]} | {module_hash} | {defs}")
    return lines


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print("\n".join(manifest_lines(sys.argv[1:])))
