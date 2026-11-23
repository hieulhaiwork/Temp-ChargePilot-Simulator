"""So hash AST từng hàm/lớp top-level giữa manifest Phase 0 và code hiện tại (sau di chuyển).

Dùng: python compare_manifest.py <phase0_manifest.txt> <moves.txt> -- <các đường dẫn quét>
`moves.txt`: mỗi dòng `old_path -> new_path` (file đã git mv). Định nghĩa ở file cũ được tìm ở file mới
hoặc ở file cũ (nếu file cũ còn là shim). Kết quả: SAME / CHANGED / MISSING cho từng định nghĩa.
"""

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MANIFEST_TOOL = HERE.parent / "phase0" / "astmanifest.py"


def parse(text: str) -> dict[str, dict[str, str]]:
    out = {}
    for line in text.splitlines():
        if line.startswith("#") or not line.strip():
            continue
        path, _, _, defs = (part.strip() for part in line.split("|"))
        items = [item.split("=", 1) for item in defs.split()]
        names = [name for name, _ in items]
        if len(names) != len(set(names)):
            raise SystemExit(f"duplicate top-level names in {path}: cannot compare by name")
        out[path] = dict(items)
    return out


def main() -> int:
    old_manifest, moves_file, _, *roots = sys.argv[1:]
    before = parse(Path(old_manifest).read_text(encoding="utf-8"))
    now = parse(
        subprocess.run([sys.executable, str(MANIFEST_TOOL), *roots], capture_output=True, text=True, check=True).stdout
    )
    moves = {}
    for line in Path(moves_file).read_text(encoding="utf-8").splitlines():
        if "->" in line:
            old, new = (p.strip() for p in line.split("->"))
            moves[old] = new
    all_now = {}
    for path, defs in now.items():
        for name, digest in defs.items():
            all_now.setdefault(name, []).append((path, digest))
    changed = 0
    for path, defs in sorted(before.items()):
        candidates = [moves.get(path, path), path]
        for name, digest in defs.items():
            hit = next((now[c][name] for c in candidates if c in now and name in now[c]), None)
            where = next((c for c in candidates if c in now and name in now[c]), None)
            if hit is None:
                elsewhere = [p for p, d in all_now.get(name, []) if d == digest]
                status = f"MOVED-SAME -> {elsewhere[0]}" if elsewhere else "MISSING"
            else:
                status = "SAME" if hit == digest else "CHANGED"
                if where != path:
                    status += f" ({where})"
            if not status.startswith(("SAME", "MOVED-SAME")):
                changed += 1
            print(f"{status:12} {path}::{name}")
    total = sum(len(defs) for defs in before.values())
    print(f"\n# definitions compared: {total}; not identical: {changed}")
    # Cổng kiểm: khác biệt / mất định nghĩa => exit 1 (không chỉ in ra).
    return 1 if changed or total == 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
