# Artifact mô hình dự báo (F6)

Thư mục chứa mô hình đã huấn luyện mà backend nạp lúc chạy
(`settings.forecast_model_path`, mặc định `src/forecast/artifacts/departure_lgbm.txt`).

- Sinh bằng `python -m src.forecast.train ...` (xem `src/forecast/train.py`).
- Mô hình LightGBM dạng text thường chỉ vài MB, nên commit thẳng vào đây để Render build
  từ git là có file. `data/` bị `.gitignore` nên không đặt artifact ở đó.
- File lớn hơn khoảng 20 MB thì không commit; chuyển sang tải lúc khởi động và ghi ADR.
- Mỗi lần cập nhật artifact phải ghi vào commit message: nguồn dữ liệu, mốc chia
  train/test và MAE trên tập test.
