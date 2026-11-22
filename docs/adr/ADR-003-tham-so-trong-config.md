# ADR-003: Tham số mô phỏng nằm trong `config/*.yaml`

- Trạng thái: Proposed. **Sửa đổi một phần — xem ghi chú bên dưới.**
- Ngày: 2026-11-16


> **Sửa đổi một phần:** [ADR-010](ADR-010-bai-hybrid-ac-dc.md) và [ADR-012](ADR-012-mot-danh-muc-xe-va-kich-ban.md), 2026-11-21: quyết định "tham số trong `config/`" giữ nguyên và áp cả cho simulator. Giá trị 8 × 7 kW / 35 kW thay bằng fixture hybrid `mvp1` (ADR-010). `vehicles.yaml` là danh mục duy nhất, provenance theo từng trường thay cờ `verified`; kịch bản của simulator chuyển về `config/scenarios/`, validator duy nhất là `Scenario.parse` (ADR-012).

## Bối cảnh

PRD §1 và §10 yêu cầu: cấu hình mô phỏng (8 × 7 kW, 35 kW, bước 15', horizon 24h) là
**tham số cấu hình**, không phải số đo thực tế. Phân tích độ nhạy cần đổi tham số
mà không sửa code. Danh mục xe (FR2), biểu giá (MT3) và kịch bản sự cố (FR18) cũng là dữ liệu.

## Các lựa chọn

1. Hằng số trong Python: nhanh, nhưng mỗi lần đổi là sửa code, và mentor khó review.
2. Biến môi trường: không hợp với dữ liệu có cấu trúc như danh sách đầu nối hay biểu giá nhiều khung.
3. **File YAML trong `config/`, validate bằng Pydantic lúc nạp.**

## Quyết định

Chọn (3). Một chỗ đọc duy nhất là `src/services/catalog.py`. File sai thì raise ngay lúc
nạp, không chạy tiếp với số liệu hỏng. Ví dụ: biểu giá hở hoặc chồng khung, `connector_id`
trùng, kịch bản có sự cố ngoài thời lượng.

- `config/` được track trong git (khác `data/` bị `.gitignore`) và được COPY vào image Docker.
- `tests/test_services/test_catalog.py` khoá giá trị PRD. Đổi tham số phải sửa PRD trước, rồi YAML, rồi test.
- `src/config.py` (Settings, biến môi trường) chỉ giữ lựa chọn hạ tầng: simulator backend, đường dẫn model, secret.

## Hệ quả

- Giờ trong YAML phải đặt trong ngoặc kép (`"22:00"`). Nếu không, PyYAML đọc thành số cơ số 60.
- `vehicles.yaml` và `tariff.yaml` hiện là dữ liệu MẪU (`verified: false`), phải thay bằng dữ liệu có nguồn trước Demo Day.
- Kết quả nạp được cache (`lru_cache`), nên đổi YAML phải khởi động lại server.
