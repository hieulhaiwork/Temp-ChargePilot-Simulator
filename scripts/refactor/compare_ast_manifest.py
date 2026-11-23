"""Cổng kiểm "chỉ di chuyển": so hash từng định nghĩa top-level của manifest cũ với code hiện tại (ADR-019).

Dùng:
    python scripts/refactor/compare_ast_manifest.py <manifest_cũ> [--moves moves.txt] -- <đường dẫn quét> ...

`moves.txt`: mỗi dòng `đường_dẫn_cũ -> đường_dẫn_mới`. Định nghĩa của file cũ được tìm ở file mới, rồi ở file cũ (nếu
file cũ còn), rồi ở BẤT KỲ file nào có cùng tên + cùng hash (MOVED-SAME, cho định nghĩa đổi file).

Exit 0 chỉ khi mọi định nghĩa của manifest cũ có mặt với hash y hệt. Exit 1 khi có định nghĩa CHANGED / MISSING,
khi manifest rỗng, hoặc khi một file có hai định nghĩa trùng tên (không so theo tên được).
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ast_manifest import manifest_lines  # noqa: E402


class DuplicateNameError(ValueError):
    pass


def parse(lines: list[str]) -> dict[str, dict[str, str]]:
    out = {}
    for line in lines:
        if line.startswith("#") or not line.strip():
            continue
        path, _, _, defs = (part.strip() for part in line.split("|"))
        items = [item.split("=", 1) for item in defs.split()]
        names = [name for name, _ in items]
        if len(names) != len(set(names)):
            raise DuplicateNameError(f"duplicate top-level names in {path}: cannot compare by name")
        out[path] = dict(items)
    return out


def compare(before: dict, now: dict, moves: dict[str, str]) -> tuple[list[str], int]:
    by_name: dict[str, list[tuple[str, str]]] = {}
    for path, defs in now.items():
        for name, digest in defs.items():
            by_name.setdefault(name, []).append((path, digest))
    report, bad = [], 0
    for path, defs in sorted(before.items()):
        candidates = [moves.get(path, path), path]
        for name, digest in defs.items():
            where = next((c for c in candidates if c in now and name in now[c]), None)
            if where is None:
                elsewhere = [p for p, d in by_name.get(name, []) if d == digest]
                status = f"MOVED-SAME -> {elsewhere[0]}" if elsewhere else "MISSING"
            else:
                status = "SAME" if now[where][name] == digest else "CHANGED"
                if where != path:
                    status += f" ({where})"
            if not status.startswith(("SAME", "MOVED-SAME")):
                bad += 1
            report.append(f"{status:12} {path}::{name}")
    return report, bad


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--" not in argv:
        print("usage: compare_ast_manifest.py <manifest> [--moves FILE] -- <roots>", file=sys.stderr)
        return 2
    split = argv.index("--")
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest")
    parser.add_argument("--moves")
    args = parser.parse_args(argv[:split])
    roots = argv[split + 1 :]
    try:
        before = parse(Path(args.manifest).read_text(encoding="utf-8").splitlines())
        now = parse(manifest_lines(roots))
    except DuplicateNameError as exc:
        print(f"ERROR: {exc}")
        return 1
    moves = {}
    if args.moves:
        for line in Path(args.moves).read_text(encoding="utf-8").splitlines():
            if "->" in line:
                old, new = (p.strip() for p in line.split("->"))
                moves[old] = new
    report, bad = compare(before, now, moves)
    print("\n".join(report))
    total = sum(len(defs) for defs in before.values())
    print(f"\n# definitions compared: {total}; not identical: {bad}")
    return 1 if bad or total == 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
