# ADR-002: Guard dispatcher là cửa duy nhất tới simulator

- Trạng thái: Proposed. **Sửa đổi một phần — xem ghi chú bên dưới.**
- Ngày: 2026-11-16


> **Sửa đổi một phần:** [ADR-011](ADR-011-mot-simulator-sau-be-mat-cong-khai.md), 2026-11-21: chokepoint giữ nguyên. `src/simulator/base.py` thành bề mặt công khai duy nhất của `HybridSimulator` v1.2 (`StationReader`, `StationActuator`, `HybridStation`, `build_algorithms`, `check_power_plan`). Luật công suất ba tầng chỉ có một cài đặt (Guard vật lý), `src/guard/rules.py` gọi lại. Hệ quả "benchmark đi chung đường Guard" chỉ áp cho benchmark nghiệm thu; chạy research / what-if chỉ có Guard vật lý, nên MT4 / MT6 đo ở đường sản phẩm.
>
> **Hiện trạng 2026-11-22 ([ADR-016](ADR-016-livestation-cho-backend.md)):** chokepoint giữ nguyên và đã chạy thật: `src/guard/dispatcher.py` là chỗ duy nhất gọi `apply_commands`, trên `LiveStation`. `HybridStation` / bề mặt mới của ADR-011 chưa làm.

## Bối cảnh

Đây là cam kết an toàn trung tâm của sản phẩm và được chấm trực tiếp:

- NFR: "LLM **không bao giờ** gửi lệnh thẳng tới simulator"; "Bộ kiểm tra là code xác định".
- FR12 / AC6 / MT6: 100% lệnh qua bộ kiểm tra; lệnh vi phạm bị chặn, ghi log, **không tới simulator**.
- FR13: bảo vệ khẩn cấp độc lập với AI.

Nếu chỉ dựa vào quy ước bằng lời, một lời gọi `sim.apply(...)` viết vội lúc gấp deadline
sẽ phá cam kết này mà không ai biết.

## Các lựa chọn

1. Quy ước bằng lời + code review.
2. **Ràng buộc bằng cấu trúc + test**: tách interface simulator thành phần đọc và phần
   ghi, chỉ một module được dùng phần ghi, và CI kiểm tra điều đó.

## Quyết định

Chọn (2):

- `src/simulator/base.py`: `StationReader` (reset/step/state) và `StationActuator`
  (`apply_commands`). Đặt tên `apply_commands` (không phải `apply`) để có thể tìm bằng AST
  mà không nhầm với `DataFrame.apply`.
- `src/guard/dispatcher.py` là module DUY NHẤT nhận `StationActuator`. Luồng: checker →
  approval → `apply_commands` → decision log. Lệnh đã duyệt được kiểm Guard lần 2 trước khi apply.
- `tests/test_architecture.py`: fail nếu file nào khác import `StationActuator` hoặc
  gọi `.apply_commands`; fail nếu `src/agents` import `guard`, `optimizer` hay `simulator`;
  fail nếu `src/guard` import Agent hoặc LLM.

## Hệ quả

- Benchmark và vận hành thật đi chung đường Guard, nên con số "0 lần vượt giới hạn" (MT4) đo trên đúng code production.
- Composition root (`simulation_service`, sau này là lifespan) phải tự đưa actuator cho dispatcher. Đây là chỗ duy nhất cần review kỹ.
- Lệnh của vận hành (xếp tay S6) cũng đi qua Guard, không có cửa sau.
