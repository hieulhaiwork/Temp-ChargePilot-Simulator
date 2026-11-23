# EXPECTED_FAILURES — test / consumer tạm hỏng trong refactor Unified Core

> Quy tắc (PLAN.md): không xoá test, không làm yếu safety check để che lỗi. Mỗi mục ghi test / consumer nào, vì sao,
> commit nào sẽ sửa. Test bị xoá cùng code đã xoá nằm ở `DELETION_MANIFEST.md`, không ở đây.

## Phase 3 (nhánh `feature/unified-core-p3`, tới commit của `PHASE3_REPORT.md`)

**Test tự động:** không có test fail. `pytest` backend 468 passed + 8 skipped; `pytest src/simulator/tests` 163 passed
(log ở `docs/refactor/raw/phase3/`).

**Consumer biết là hỏng / lệch (chưa có test bắt), sửa ở Phase 4 mục 3:**

| Consumer | Hiện tượng | Vì sao | Sửa |
|---|---|---|---|
| Frontend S8 (`frontend/src/app/operator/simulation/page.tsx`) | Dropdown còn A_fcfs / A_edf / B / C / D; chọn thì `POST /simulation/runs` trả 404 `not_found` ("đã bỏ ở Phase 3") | LP backend A–D đã xoá; enum `StrategyName` + OpenAPI cố ý chưa đổi để không đụng hợp đồng API trong Phase 3 | Phase 4: bỏ giá trị A–D khỏi `StrategyName`, `export_openapi.py`, `npm run gen:api`, dropdown |
| `GET /simulation/benchmark` | Trả `eval/results/benchmark.json` cũ (có dòng A–D, số trước refactor) | Phase 3 không được ghi `eval/results/` | Phase 4: sinh lại sau nghiệm thu cuối (cần chủ dự án duyệt) |
| `STATION_ENGINE=live` | App không khởi động (pydantic từ chối giá trị) | LiveStation đã xoá; `render*.yaml`, `.env.example` đều là `hybrid` | Không cần sửa; ghi để người deploy biết |
| `eval/build_simulator_evidence.py`, `eval/run_manual_agent_evidence.py` | Chuỗi mô tả còn nhắc LiveStation / A–D | Script sinh evidence lịch sử, không chạy trong CI | Phase 4 (dọn tài liệu lỗi thời) |
| `make web-check` | Chưa chạy trong Phase 3 | OpenAPI không đổi (`export_openapi.py --check` OK) nên type frontend không đổi | Phase 4 nghiệm thu E2E |
