"""CLI huấn luyện LightGBM dự báo thời điểm rút đầu nối (T2.3).

Chạy từ repo root:
    python -m src.forecast.train --source norway_2024 --test-from 2024-10-01

Ghi artifact vào src/forecast/artifacts/ (mô hình nhỏ, commit được để Render có file
khi build — xem artifacts/README.md). Cần lightgbm + pandas (đang để comment trong
requirements.txt, bật khi làm task này).

Owner: TV2. Trạng thái: STUB.
"""

import argparse
from pathlib import Path

from src.models.simulation import SessionSource

DEFAULT_OUT = Path(__file__).resolve().parent / "artifacts" / "departure_lgbm.txt"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Huấn luyện mô hình dự báo thời điểm rút đầu nối (F6)")
    parser.add_argument("--source", type=SessionSource, default=SessionSource.NORWAY_2024)
    parser.add_argument("--test-from", required=True, help="Ngày bắt đầu tập test (ISO 8601), chia theo thời gian")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.parse_args(argv)
    raise NotImplementedError("[T2.3] train — load_sessions → temporal_split → build_features → LightGBM → --out")


if __name__ == "__main__":
    raise SystemExit(main())
