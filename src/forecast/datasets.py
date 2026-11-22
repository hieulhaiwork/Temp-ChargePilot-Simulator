"""Nạp & chuẩn hoá dữ liệu phiên sạc về ChargingSession (T1.3).

Nguồn (PRD §8):
  - Na Uy 2024 — khu dân cư: 35.377 phiên, 267 người dùng → huấn luyện F6
  - Na Uy 2021 — chung cư: 6.878 phiên, 97 người dùng   → kiểm tra chéo môi trường chung cư
  - ACN-Data (Caltech)                                    → mốc so sánh, khớp ACN-Sim

Dữ liệu thô đặt ở data/raw/<nguồn>/ — thư mục data/ đã .gitignore, KHÔNG commit dữ liệu.
Ghi rõ link tải + license của từng nguồn trong notebooks/README.md.

Giới hạn dữ liệu: KHÔNG có nhãn thời gian chờ, xe đặt trước không đến, lúc xe rời ô đỗ
→ các chỉ số đó chỉ đo trong mô phỏng, có nêu giả định.

Owner: TV2. Trạng thái: STUB.
"""

from datetime import datetime
from pathlib import Path

from src.models.charging import ChargingSession
from src.models.simulation import SessionSource

RAW_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"


def load_sessions(source: SessionSource) -> list[ChargingSession]:
    """Đọc data/raw/<source>/ → ChargingSession (đổi múi giờ, giả danh user_id)."""
    raise NotImplementedError("[T1.3] load_sessions — parser cho từng nguồn dữ liệu")


def temporal_split(
    sessions: list[ChargingSession], test_from: datetime
) -> tuple[list[ChargingSession], list[ChargingSession]]:
    """PRD §8: chia theo THỜI GIAN (và theo địa điểm qua field `site`) — không chia ngẫu nhiên."""
    raise NotImplementedError("[T2.3] temporal_split — train < test_from ≤ test")
