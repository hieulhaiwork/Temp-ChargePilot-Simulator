# Notebooks — khám phá dữ liệu (T1.3, TV2)

Nơi để EDA và thử nghiệm nhanh. Code dùng lại được phải chuyển vào `src/forecast/`
và có test, vì notebook không phải nơi chứa logic production.

## Dữ liệu (PRD §8)

| Nguồn | Dùng để | Đặt file thô ở |
|---|---|---|
| Na Uy 2024 — khu dân cư, 35.377 phiên, 267 người dùng | Học hành vi cắm/rút; train F6 | `data/raw/norway_2024/` |
| Na Uy 2021 — chung cư, 6.878 phiên, 97 người dùng | Kiểm tra chéo môi trường chung cư | `data/raw/norway_2021/` |
| ACN-Data (Caltech) | Mốc so sánh; khớp ACN-Sim | `data/raw/acn/` |

Ghi vào bảng trên link tải và license của từng nguồn khi tải về.
`data/` đã nằm trong `.gitignore` và `.dockerignore`, nên KHÔNG commit dữ liệu.

## Quy ước

- Đặt tên theo `NN_<chu-de>.ipynb` (vd `01_eda_norway_2024.ipynb`).
- Xoá output trước khi commit để diff gọn và không lộ dữ liệu.
- Chia train/test theo **thời gian và địa điểm**, không chia ngẫu nhiên (PRD §8).
- Không dùng giờ rút thật (`unplug_time`) làm feature (FR17).
- Dữ liệu không có nhãn thời gian chờ, no-show hay lúc xe rời ô đỗ. Chỉ số nào cần những
  nhãn này thì chỉ đo trong mô phỏng và phải ghi rõ giả định.
