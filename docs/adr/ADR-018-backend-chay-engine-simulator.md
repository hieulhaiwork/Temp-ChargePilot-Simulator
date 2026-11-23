# ADR-018: Backend chạy engine simulator R&D (HybridStation + thuật toán M2b / M3a / M3b) — simulator là gốc

- Trạng thái: Proposed — nhóm chốt hướng 23/11 ("simulator là phần gốc, sửa backend cho trùng"), chờ duyệt
- Ngày: 2026-11-23
- Liên quan: **thay thế phần quyết định của ADR-016** (LiveStation cho backend); ADR-011 (một simulator), ADR-002, ADR-017

## Bối cảnh

ADR-016 đặt `LiveStation` cho backend vì ba lý do. Kiểm lại 23/11:

1. "HybridSimulator chạy trọn kịch bản, tự dispatch" — đúng với `HybridSimulator.step()`, nhưng engine đã tách thành các
   thành phần dùng lại được: `QueueController`, `EV2GymAdapter`, dispatch / coordinator / optimizer (`resolve_algorithms`),
   `safety/guard.py`. Backend ghép lại được mà không sửa engine, và đặt Guard backend vào giữa.
2. "ev2gym nặng" — cài `--no-deps` như `src/simulator/requirements-ci.txt`: import engine thêm ≈ 58 MB, chạy trọn `mvp1`
   0,07 s (đo 23/11 trong venv `.simulator`).
3. "Phải sửa code của người làm simulator" — không cần (mục Quyết định).

## Quyết định

1. **Trạm**: `src/simulator/hybrid_station.py:HybridStation` cài `StationReader` + `StationActuator`, vật lý = engine
   simulator (AC EV2Gym, DC theo `dc_charging_model`, `validate_response`, Guard sau áp). Mặc định `STATION_ENGINE=hybrid`;
   `live` (LiveStation) chỉ để dự phòng.
2. **Thuật toán**: `src/services/hybrid_planner.py:SimulatorScheduler` ghép đúng các bước của `HybridSimulator.step`
   (dispatch → coordinator → optimizer theo vùng → Guard simulator) trên trạng thái thật của trạm, trả `SchedulePlan`.
   Chiến lược `B0`, `M2b`, `M3a`, `M3b` lấy từ `src/simulator/benchmark_mvp3.py POLICIES`. Chạy thật mặc định `M3a`
   (`LIVE_STRATEGY`, policy tham chiếu cho demo theo `SIMULATOR_INTEGRATION_CONTRACT.md` §2). A–D giữ làm đối chứng.
3. Lệnh vẫn qua `diff_commands` → `guard/dispatcher.py` (ADR-002); lớp vật lý của Guard là Guard simulator (ADR-017).
4. Không sửa `src/simulator/src/`, `src/simulator/tests/`, `scenario/`, `config/` của simulator. Backend chỉ dùng phần
   nội bộ (`queue.sessions`, `adapter.models`) để thêm xe đến giữa chừng.

## Hệ quả

- Web chạy cùng vật lý và cùng thuật toán với số MVP-2 / MVP-3. Benchmark backend ghi rõ engine trong mọi báo cáo.
- [GIẢ ĐỊNH] khác HybridSimulator.run(): khoảng quyết định 15' / theo sự kiện (setpoint giữ, trạm tự cắt theo đường sạc
  mỗi phút); biểu giá backend đổi sang `Tariff` simulator; consent "được lùi giờ bắt đầu tối đa" được backend áp SAU
  optimizer simulator (`_start_minimums` + `_fit_with_minimums`: ép mức tối thiểu, co xe khác cho vừa tủ / vùng / lưới, Guard
  simulator kiểm lại) — cùng quy tắc với LP backend; tạm dừng sau khi đã sạc vẫn chờ nhóm chốt.
- Trạm có `RLock`: bộ lập lịch đọc trạm trên thread solver, request khác có thể `step()` cùng lúc.
- Image backend cần `ev2gym` (`--no-deps`) + `gymnasium`.
- Số liệu cũ trong `eval/evidence/2026-11-22/` là của LiveStation — giữ nguyên, không trộn với lượt chạy mới.
- Bằng chứng [`eval/evidence/2026-11-23/`](../../eval/evidence/2026-11-23/README.md): trạm phát lại `mvp1` khớp
  HybridSimulator trong 1e-6 kWh; benchmark 90 lượt 0 vi phạm. Trên kịch bản backend, M3a / M3b rẻ hơn A_edf ~14–16% nhưng
  đúng hạn thấp hơn → **chọn chiến lược mặc định (`LIVE_STRATEGY`) vẫn là câu hỏi mở cho nhóm**; M3a giữ theo contract.
