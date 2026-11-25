# Demo AI-4.4A · WHY và WHAT-IF

Demo chạy trên SQLite tạm với DecisionTrace và booking tổng hợp. Giải thích, chỉ số và kết quả được tạo từ WHY Engine G2 và WHAT-IF Engine G4. Runtime dùng đồng hồ mô phỏng và fixture chung với integration tests.

## Chạy demo qua API

Từ thư mục gốc `P-019`, chạy bằng môi trường Python đã cài dependencies của backend.

```bash
.simulator/bin/python eval/evidence/2026-11-26-ai4-4-4a/run_demo.py --out /tmp/chargepilot-g6a-demo.json
```

Script chạy toàn bộ request qua FastAPI và dùng JWT thật cho tài khoản fixture. JSON giữ kết quả, claims, evidence refs, cutoff và job envelope đã lọc theo actor. File không chứa token. [Script](../../eval/evidence/2026-11-26-ai4-4-4a/run_demo.py)

## Chạy demo trên dashboard

Terminal backend từ repository root.

```bash
.simulator/bin/python eval/evidence/2026-11-26-ai4-4-4a/run_demo.py --serve
```

Terminal frontend với Node tương thích `package-lock.json`.

```bash
cd frontend
npm ci
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000 npm run dev
```

Mở `http://localhost:3000/login`. Tài khoản fixture đều có mật khẩu `fixture-only-passphrase`.

| Vai trò | Email fixture | Dashboard |
|---|---|---|
| Resident | `res-resident-demo@g6a.example` | `/resident` |
| Operator | `operator@g6a.example` | `/operator` |

1. Resident hỏi **Tại sao xe của tôi vẫn chưa được sạc?** Mở Bằng chứng để xem decision time, stage và refs của WHY.
2. Resident hỏi **Nếu tôi chỉ cần sạc đến 75% thay vì 90% thì sao?** Sau polling, xem cam kết 90% ở cả hai nhánh và cam kết sửa 75% riêng, cùng thời điểm đạt mục tiêu và rời cổng nếu đã quan sát.
3. Operator chọn đầu nối DC có tải mà script in khi khởi động, rồi hỏi **Nếu một cổng DC bị lỗi trong 30 phút thì sao?** Xem KPI và danh sách booking ảnh hưởng trong phạm vi vận hành. Hai cổng DC được seed có tải ở snapshot. Câu hỏi này cần chọn đầu nối vì trạm có nhiều cổng phù hợp.
4. Dùng biểu mẫu Operator để đổi giới hạn đầu vào lưới xuống 15 kW trong cửa sổ 8 phút. Kết quả nêu rõ đơn vị phía lưới và phía đầu ra bộ sạc.
5. Operator hỏi **Cần tăng công suất nguồn lên bao nhiêu để tất cả xe sạc đúng hạn?** Router trả `feature_not_available` cho HOW-TO.

## Hợp đồng HTTP

Gửi JWT trong header `Authorization: Bearer …`. Chỉ thị dưới đây dùng giờ của fixture, còn `GET /api/v1/copilot/context` cung cấp station clock, timezone, booking và connector choices theo quyền hiện tại.

| Request | JSON minh họa | Kết quả |
|---|---|---|
| `POST /api/v1/copilot/why` | `{"subject_scope":"own_booking","topic":"queue","at":"2026-11-23T12:01:00+07:00"}` | 200, `kind=why`, authorized result và grounded claims |
| `POST /api/v1/copilot/what-if` | `{"patch":{"op":"revise_vehicle","booking_id":"resident-demo","target_soc":75},"horizon_minutes":120}` | 202, `kind=job`, `job.job_kind=what_if` |
| `POST /api/v1/copilot/query` | `{"message":"Nếu một cổng DC bị lỗi trong 30 phút thì sao?","selected_connector_id":"DC-01-1"}` | 202 khi authorized và connector hợp lệ, hoặc notice nếu cần làm rõ |
| `GET /api/v1/copilot/jobs/{job_id}` | — | 200 cho job thuộc caller |
| `DELETE /api/v1/copilot/jobs/{job_id}` | — | 200 cho yêu cầu hủy job thuộc caller |
| `POST /api/v1/copilot/query` | `{"job_id":"<id do server cấp>"}` | 200 cho follow-up trên job còn trong TTL của caller |

Ứng dụng trả 401 khi thiếu JWT và 404 khi truy cập job của actor khác. `clarify`, `unsupported`, `structured_fallback` và `feature_not_available` là notices có code. Tác vụ chạy trong bộ nhớ một worker. Cancellation dừng coroutine và chặn work tiếp theo, trong khi native solver call đã bắt đầu có thể chạy đến hết.

Ở lần chạy demo này provider dùng deterministic fallback. UI cũng có biểu mẫu WHY/WHAT-IF với cùng engine và validation. [OpenAPI](../../frontend/openapi.json)
