import ast
import subprocess
import sys

a, b, root = sys.argv[1], sys.argv[2], sys.argv[3]
files = subprocess.run(
    ["git", "ls-tree", "-r", "--name-only", b, "--", root], capture_output=True, text=True
).stdout.split()


def src(rev, f):
    r = subprocess.run(["git", "show", f"{rev}:{f}"], capture_output=True)
    return r.stdout.decode("utf-8") if r.returncode == 0 else None


def norm(t):
    tree = ast.parse(t)
    for n in ast.walk(tree):  # drop docstrings
        if (
            isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef))
            and n.body
            and isinstance(n.body[0], ast.Expr)
            and isinstance(getattr(n.body[0], "value", None), ast.Constant)
            and isinstance(n.body[0].value.value, str)
        ):
            n.body = n.body[1:] or [ast.Pass()]
    return ast.dump(tree)


for f in files:
    if not f.endswith(".py"):
        continue
    x, y = src(a, f), src(b, f)
    if x is None:
        print("NEW      ", f)
        continue
    print("SAME_AST " if norm(x) == norm(y) else "DIFF_AST ", f)
