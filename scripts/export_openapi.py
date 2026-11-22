#!/usr/bin/env python3
"""Chụp hợp đồng API của backend ra `frontend/openapi.json` (ADR-008, ADR-009).

Đây là THỨ DUY NHẤT frontend nhận từ backend: `npm run gen:api` (trong frontend/) đọc file này và
sinh `frontend/src/lib/api/schema.d.ts`. Không gõ tay DTO ở phía web.

    python scripts/export_openapi.py            # ghi lại file sau khi đổi model / endpoint
    python scripts/export_openapi.py --check    # CI: exit 1 nếu file đã commit lệch với code

File được ghi ổn định (sort_keys, LF, UTF-8) để diff trong PR chỉ hiện thay đổi thật.
`tests/test_api/test_openapi_snapshot.py` chạy cùng phép so sánh trong pytest.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SNAPSHOT_PATH = ROOT / "frontend" / "openapi.json"


def render_openapi() -> str:
    """OpenAPI hiện tại của app, ở dạng văn bản ổn định."""
    from src.main import app  # import muộn: --help không cần nạp cả ứng dụng

    return json.dumps(app.openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ghi / kiểm frontend/openapi.json từ FastAPI app")
    parser.add_argument("--check", action="store_true", help="Không ghi; exit 1 nếu file lệch với code")
    parser.add_argument("--out", type=Path, default=SNAPSHOT_PATH)
    args = parser.parse_args(argv)

    current = render_openapi()
    if args.check:
        if not args.out.is_file():
            print(f"THIẾU {args.out} — chạy: python scripts/export_openapi.py", file=sys.stderr)
            return 1
        if args.out.read_text(encoding="utf-8") != current:
            print(
                f"{args.out.relative_to(ROOT)} đã CŨ so với code — chạy: python scripts/export_openapi.py "
                "rồi `npm run gen:api` trong frontend/",
                file=sys.stderr,
            )
            return 1
        print(f"OK — {args.out.relative_to(ROOT)} khớp với code.")
        return 0

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(current, encoding="utf-8", newline="\n")
    print(f"==> Đã ghi {args.out}")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):  # console Windows (cp1258) không in được tiếng Việt có dấu
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
