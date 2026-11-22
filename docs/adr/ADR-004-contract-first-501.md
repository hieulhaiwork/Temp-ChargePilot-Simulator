# ADR-004: Skeleton contract-first — đủ schema, stub trả HTTP 501 kèm mã task

- Trạng thái: Proposed
- Ngày: 2026-11-16

## Bối cảnh

4 thành viên làm song song từ tuần 1. Frontend (TV4) cần API để dựng màn S1–S8 trước khi
backend xong. TV1, TV2, TV3 cần thống nhất kiểu dữ liệu trao đổi (`ChargeRequest`,
`SchedulePlan`, `Command`…) trước khi viết thuật toán.

## Các lựa chọn

1. Mỗi người tự định nghĩa kiểu khi cần: nhanh lúc đầu, nhưng ráp vào tuần 3 thì vỡ.
2. **Contract-first**: định nghĩa đủ model + chữ ký hàm + endpoint ngay. Thân hàm chưa làm
   thì `raise NotImplementedError("[Txx] mô tả")`, và app map lỗi này sang HTTP 501.

## Quyết định

Chọn (2):

- `src/models/*` là hợp đồng dữ liệu đầy đủ, có validator, và đã có test.
- Mọi endpoint đã đăng ký nên hiện trên `/docs` với đủ schema. Frontend sinh type TypeScript từ `/openapi.json`.
- `src/main.py` có handler `NotImplementedError` → `501 {"detail": "[T2.2] …", "status": "not_implemented"}`.
  Khi service được cài, endpoint tự chạy mà không phải sửa router.
- Lấy backlog từ code: `grep -rn 'NotImplementedError("\[T' src/`.
- Test cho phần chưa làm được viết sẵn dưới dạng `@pytest.mark.skip(reason="[Txx] …")`, kèm Given/When/Then trong docstring.

## Hệ quả

- `/health` và các endpoint dữ liệu tham chiếu (`/vehicles`, `/energy/estimate`, `/station/config`,
  `/tariff`, `/simulation/scenarios`) chạy thật. CI docker-smoke và Render deploy không bị ảnh hưởng.
- KHÔNG bật `control_loop.run_forever` trong lifespan khi nó còn là stub, nếu không app sẽ không khởi động được.
- Skip test phải được bỏ `skip` khi làm task tương ứng. Review PR cần kiểm tra điều này.
