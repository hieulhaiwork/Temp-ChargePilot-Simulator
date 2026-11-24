# Plan 40 — Database và persistence

> **Cập nhật 21/11/2026 theo ADR-010…015.** Đọc §0 trước. Từ §1 trở đi mô tả 9 bảng đang có trong
> `src/db/tables.py` + `migrations/versions/0001_initial_schema.py` (vẫn đúng với code). Bảng thay đổi tổng:
> [00-overview §0](00-overview.md).

## 0. Cập nhật 21/11 — bảng còn thiếu cho AI-1 / AI-4 (việc cần làm, CHƯA có migration)

[ADR-014](../adr/ADR-014-decision-trace-counterfactual-hitl.md) cần lưu vòng đời đề nghị, sự đồng ý của cư dân, các lần
sửa cam kết theo thời điểm, và audit. Bốn bảng dưới đây **chưa có trong `src/db/tables.py`, chưa có migration**. Tên
cột chỉ là gợi ý từ master context v1.0 (Hiếu, 20/11 — chưa đưa vào repo) §8.3, §10.4; chốt khi viết migration
(ADR-005: sửa `tables.py` → `alembic revision --autogenerate` → đọc lại file sinh ra).

| Bảng | Mục đích | Trường cần có (gợi ý, chưa chốt) |
|---|---|---|
| `proposals` | Đề nghị AI-1 / thay đổi cần duyệt; vòng đời `PROPOSED → APPROVED / REJECTED / EXPIRED → APPLIED / APPLY_FAILED` | `proposal_id`, `booking_id` / xe, `state_version`, `expires_at`, `status`, option đã mô phỏng (payload), `evidence_ref` |
| `consents` | Quyết định đồng ý / từ chối của cư dân hoặc vận hành | `proposal_id`, `actor_id`, `role`, `decision`, `decided_at`, khoá idempotency |
| `vehicle_revisions` | Sửa cam kết (target SOC, deadline) **có hiệu lực từ thời điểm T**; không ghi đè lịch sử | `booking_id`, `revision_no`, `effective_at`, giá trị trước / sau, `proposal_id` |
| `audit_log` | Nhật ký chỉ thêm cho approval, apply, từ chối, stale | `seq`, `actor_id`, `action`, `target`, `state_version`, `at` |

Quan hệ với bảng cũ: `approvals` (FR13, lệnh điều khiển) và `decision_log` (FR14) giữ nguyên; cách gộp hay tách với
`proposals` / `audit_log` **chưa quyết** (ghi ở mục conflict của handoff). Trạng thái vật lý (SOC, công suất) vẫn chỉ
lấy từ runtime simulator — DB không giữ "SOC sự thật" riêng.

Đoạn cũ bị ảnh hưởng: §1 "Không lưu trong DB … artifact F6" — F6 HOÃN (ADR-015), không có artifact trong sprint.

> Trạng thái: đề xuất Pha A, chờ duyệt (ADR-005, D1, D2). Owner: TV3. Task chính: T1.6.
> Interface hiện có: `src/services/repository.py` (10 hàm, đều là stub `[T1.6]`).

## 1. Mục tiêu và phạm vi

Lưu bền những gì **không được mất** khi Render ngủ hoặc redeploy: tài khoản, booking, lịch gần nhất, phê duyệt, nhật
ký quyết định (FR14), thông báo. Cùng một code chạy trên SQLite (máy local, CI) và Postgres của Neon (deploy).

| Lưu trong DB | Không lưu trong DB |
|---|---|
| `users`, `bookings`, `idempotency_keys`, `schedule_plans`, `approvals`, `decision_log`, `notifications`, `station_events`, `load_points` | Tham số trạm / xe / giá / kịch bản (`config/*.yaml`, ADR-003) · báo cáo benchmark (`eval/results/benchmark.json`) · artifact F6 · trạng thái simulator và checkpoint chat (RAM, dựng lại khi khởi động) · dữ liệu của lần chạy benchmark (sinks ghi vào bộ nhớ, 10 §5.1) |

## 2. Cấu trúc thư mục (tới từng file)

```text
src/
├── db/                          🆕 package DUY NHẤT biết SQLAlchemy
│   ├── __init__.py
│   ├── base.py                  DeclarativeBase + naming convention cho khoá / index
│   ├── types.py                 UtcDateTime (TypeDecorator), JSON có variant JSONB cho Postgres
│   ├── tables.py                9 lớp ORM (mục 3)
│   ├── session.py               make_engine(url), session_scope(), chuẩn hoá URL Neon
│   └── mappers.py               Pydantic ↔ hàng ORM cho từng bảng
├── services/repository.py       cửa DUY NHẤT của tầng ứng dụng tới DB (mục 5)
└── models/identity.py           🆕 UserRecord (Pydantic, có password_hash — không xuất hiện trên API)
alembic.ini                      🆕 repo root
migrations/                      🆕 env.py, script.py.mako, versions/0001_initial.py
tests/
├── test_services/test_repository.py     🆕 round-trip từng bảng, append-only, idempotency
├── test_db/test_migrations.py           🆕 `alembic upgrade head` khớp Base.metadata
└── test_architecture.py                 + luật: chỉ src/db/** và services/repository.py import sqlalchemy / src.db
```

Luật ranh giới mới (khoá bằng test):

1. `sqlalchemy` và `src.db` chỉ được import trong `src/db/**` và `src/services/repository.py`.
2. `src/db/**` chỉ import `src.models`, `src.config`; không import `agents`, `api`, `services`, `guard`, `optimizer`, `simulator`, `forecast`.
3. `src/models/**` không import `sqlalchemy` (giữ nguyên luật hiện có: không import package nào khác trong `src/`).

## 3. Mô hình dữ liệu

### 3.1 Cách lưu: cột khoá + `payload` JSON

Hợp đồng dữ liệu đã là Pydantic lồng nhau (`Booking` chứa `ChargeRequest`, `EnergyEstimate`, `ConsentScope`). Mỗi bảng
nghiệp vụ lưu:

- các **cột khoá** phục vụ lọc, sắp xếp, ràng buộc (id, `resident_id`, `status`, mốc thời gian…);
- một cột `payload` chứa `model_dump(mode="json")` của cả model. `payload` là bản gốc khi đọc lại.

Lý do không chuẩn hoá từng field lồng nhau thành bảng: 4 tuần, contract còn thay đổi; mỗi lần thêm field Pydantic sẽ
không cần migration. Cái giá phải trả: cột khoá trùng thông tin với `payload`, nên `mappers.py` là chỗ duy nhất ghi cả
hai và có test round-trip. Phương án chuẩn hoá hoàn toàn được ghi trong ADR-005 như lựa chọn đã cân nhắc.

### 3.2 ERD

```mermaid
erDiagram
    USERS ||--o{ BOOKINGS : "resident_id"
    USERS ||--o{ NOTIFICATIONS : "resident_id"
    BOOKINGS ||--o| IDEMPOTENCY_KEYS : "booking_id"
    BOOKINGS ||--o{ APPROVALS : "booking_id"
    APPROVALS ||--o{ NOTIFICATIONS : "approval_id"
    APPROVALS ||--o{ DECISION_LOG : "approval_id"
    BOOKINGS ||--o{ DECISION_LOG : "booking_id"
    SCHEDULE_PLANS ||--o{ BOOKINGS : "schedule_version"

    USERS {
        string user_id PK
    }
    BOOKINGS {
        string booking_id PK
    }
    IDEMPOTENCY_KEYS {
        string key PK
    }
    SCHEDULE_PLANS {
        int version PK
    }
    APPROVALS {
        string approval_id PK
    }
    DECISION_LOG {
        int seq PK
    }
    NOTIFICATIONS {
        string notification_id PK
    }
    STATION_EVENTS {
        int seq PK
    }
    LOAD_POINTS {
        datetime ts PK
    }
```

`STATION_EVENTS` và `LOAD_POINTS` là chuỗi thời gian độc lập, không có khoá ngoại.

### 3.3 Bảng, cột, khoá, index

Kiểu: `str(n)` = `String(n)`; `ts` = `UtcDateTime`; `json` = JSON / JSONB. Cột không ghi `NULL` là `NOT NULL`.

**`users`** — FR1, F8

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `user_id` | str(32) PK | giả danh, dạng `res-xxxxxxxx` / `op-xxxxxxxx` (NFR riêng tư) |
| `email` | str(254) UNIQUE | chữ thường; chỉ bảng này chứa email |
| `password_hash` | str(255) NULL | chuỗi scrypt; `NULL` sau khi xoá tài khoản |
| `role` | str(16) | `resident` / `operator` |
| `display_name` | str(80) | |
| `vehicle_model` | str(64) NULL | xe mặc định (F8) |
| `default_soc_target` | float NULL | F8 |
| `consent` | json | `ConsentScope` mặc định của cư dân (FR13) |
| `created_at`, `deleted_at` | ts, ts NULL | |

**`bookings`** — FR2, FR8, US2

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `booking_id` | str(32) PK | |
| `resident_id` | str(32) FK → users | |
| `status` | str(16) | `BookingStatus` |
| `mode` | str(16) | `reservation` / `walk_in` |
| `vehicle_model` | str(64) | |
| `connector_id` | str(8) NULL | |
| `arrival_time`, `deadline` | ts NULL, ts | |
| `planned_start`, `planned_end` | ts NULL | |
| `schedule_version` | int | |
| `created_at`, `updated_at` | ts | |
| `payload` | json | `Booking` |

Index: `(resident_id, status)`, `(status, deadline)`. Nếu Q6 được duyệt: index duy nhất **một phần** trên
`resident_id` với điều kiện `status IN ('confirmed','queued','charging')` (Postgres và SQLite đều hỗ trợ).

**`idempotency_keys`** — 10 §4.2

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `key` | str(80) PK | header `Idempotency-Key`, hoặc `chat:{session_id}` |
| `resident_id` | str(32) | |
| `request_hash` | str(64) | SHA-256 của body đã chuẩn hoá |
| `booking_id` | str(32) FK → bookings | |
| `created_at` | ts | xoá bản ghi cũ hơn 24 giờ |

**`schedule_plans`** — NFR "giữ lịch gần nhất"

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `version` | int PK | `SchedulePlan.version` |
| `strategy` | str(8) | |
| `created_at`, `horizon_start` | ts | |
| `step_minutes` | int | |
| `solve_time_s` | float NULL | MT5 |
| `payload` | json | `SchedulePlan` |

Giữ 200 phiên bản gần nhất; `save_plan` xoá bản cũ hơn.

**`approvals`** — FR13, AC4

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `approval_id` | str(32) PK | |
| `kind`, `status` | str(24), str(16) | |
| `requested_from` | str(32) | `resident_id` hoặc `operator` |
| `command_id` | str(32) | |
| `booking_id` | str(32) NULL | |
| `created_at`, `expires_at`, `decided_at` | ts, ts NULL, ts NULL | |
| `decided_by` | str(32) NULL | |
| `payload` | json | `Approval` |

Index: `(status, expires_at)` cho `expire_overdue`; `(requested_from, status)`.

**`decision_log`** — FR14, chỉ thêm

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `seq` | int PK tự tăng | thứ tự ghi; con trỏ phân trang |
| `entry_id` | str(32) UNIQUE | |
| `timestamp` | ts | |
| `command_id` | str(32) | |
| `source`, `command_type` | str(16), str(24) | |
| `connector_id` | str(8) | |
| `booking_id` | str(32) NULL | |
| `guard_passed` | bool NULL | `NULL` = không có verdict |
| `executed` | bool | |
| `approval_id` | str(32) NULL | |
| `payload` | json | `DecisionLogEntry` |

Index: `(guard_passed, seq)` cho tab "Bị Guard chặn"; `(booking_id, seq)` cho `charging_service.explain`.

**`decision_traces`** — ADR-019 Phase 4 (quyết định 6), migration `0002`. Tóm tắt vận hành của một lần tính lại; trace
chi tiết (facts cùng schema DecisionTrace của simulator) là artifact JSONL trong `DECISION_TRACE_DIR`
(`src/services/decision_trace.py`). Nối với `decision_log` qua `payload.command.correlation_id`.

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `correlation_id` | str(32) PK | cũng nằm trong `Command.correlation_id` |
| `decided_at` | ts | |
| `policy_id` | str(16) | B0 / M2b / M3a / M3b |
| `schedule_version` | int | |
| `budget_deviation_kw_max` | float | vượt assigned budget ngoài command deadband |
| `hard_violations` | int | Physical Guard sau thực thi |
| `closed` | bool | `false` = quyết định còn hiệu lực (chưa có số đo) |
| `payload` | json | `DecisionTraceSummary` |

Index: `(decided_at)`.
`repository` không có hàm sửa hay xoá bảng này; test kiểm điều đó.

**`notifications`** — FR15

| Cột | Kiểu |
|---|---|
| `notification_id` | str(32) PK |
| `resident_id` | str(32) FK → users |
| `kind`, `title`, `body` | str(32), str(120), text |
| `approval_id` | str(32) NULL |
| `created_at`, `read_at` | ts, ts NULL |

Index: `(resident_id, created_at)`.

**`station_events`** — S5 "Sự kiện gần nhất": `seq` PK tự tăng, `event_id` UNIQUE, `type`, `occurred_at`, `connector_id`
NULL, `booking_id` NULL, `payload`. Index `(occurred_at)`. Giữ 7 ngày.

**`load_points`** — S5 biểu đồ tải: `ts` PK, `total_power_kw`, `power_limit_kw`. Giữ 7 ngày (API cho tối đa 168 giờ).

## 4. SQLite local ↔ Postgres Neon

| Vấn đề | Cách xử lý |
|---|---|
| Driver | SQLite: có sẵn trong stdlib. Postgres: `psycopg` 3 (D2), URL `postgresql+psycopg://` |
| Chuỗi kết nối Neon bắt đầu bằng `postgresql://` | `session.make_engine` tự đổi tiền tố, để dán nguyên chuỗi của Neon vào `DATABASE_URL` |
| SQLite trả `datetime` **không có múi giờ**, trong khi contract dùng `AwareDatetime` | `UtcDateTime`: lúc ghi đổi sang UTC và từ chối giá trị naive; lúc đọc gắn lại UTC. Múi giờ gốc vẫn còn trong `payload` |
| JSON | Kiểu `JSON` chung, variant `JSONB` trên Postgres. Không viết truy vấn vào bên trong JSON: muốn lọc thì thêm cột khoá |
| Khoá ngoại trên SQLite tắt mặc định | Listener bật `PRAGMA foreign_keys=ON`; thêm `journal_mode=WAL` |
| SQLite không `ALTER` được nhiều thứ | Alembic `render_as_batch=True` |
| Router chạy trong threadpool | SQLite: `check_same_thread=False`. Mỗi hàm repository mở một session ngắn |
| Neon tự tạm dừng khi không dùng | `pool_pre_ping=True`, `pool_recycle=300`, `pool_size` nhỏ (≤ 5), `connect_timeout=10`; lỗi kết nối → 503 `database_unavailable` |
| Khác biệt phương ngữ lọt qua test SQLite | CI có thêm job chạy `test_repository.py` trên Postgres container (50 §4) |

Truy cập **đồng bộ** (không dùng asyncio driver): giữ được chữ ký `def` hiện có của `repository`, không phải đổi tool
của Agent. Code `async` gọi qua `asyncio.to_thread`.

`.env.example` hiện đặt `DATABASE_URL=postgresql://user:password@localhost:5432/dbname` làm giá trị mặc định: ai chép
sang `.env` sẽ không chạy được trên máy không có Postgres. Đề xuất đổi mặc định về `sqlite:///./data/app.db`.

## 5. Interface `services/repository.py`

Mười hàm hiện có giữ nguyên tên. Hàm 🆕 đều là stub `[T1.6]` cho tới khi làm.

| Nhóm | Hàm | Trạng thái |
|---|---|---|
| Vòng đời | `init(database_url=None)`, `dispose()`, `ping() -> bool` | 🆕 |
| Tài khoản | `get_user_by_email(email)`, `get_user(user_id)`, `upsert_user(record)`, `update_profile(user_id, …)`, `anonymize_user(user_id)` | 🆕 |
| Booking | `save_booking(booking, *, idempotency_key=None, request_hash=None)`, `get_booking(booking_id)`, `list_bookings(resident_id=None, statuses=None)` | 🧩 (thêm tham số) |
| | `active_booking(resident_id)`, `find_idempotent(key, resident_id, request_hash)` | 🆕 |
| Lịch | `save_plan(plan)`, `latest_plan()` | 🧩 |
| | `get_plan(version)` | 🆕 |
| Phê duyệt | `save_approval(approval)`, `list_approvals(status=None, requested_from=None)` | 🧩 (thêm tham số) |
| | `get_approval(approval_id)`, `overdue_approvals(now)` | 🆕 |
| Nhật ký | `append_decision(entry)`, `list_decisions(limit=100, blocked_only=False, before=None, booking_id=None)` | 🧩 (thêm tham số) |
| Thông báo | `list_notifications(resident_id)` | 🧩 |
| | `add_notification(resident_id, notification)`, `mark_notification_read(notification_id, resident_id)` | 🆕 |
| Chuỗi thời gian | `append_event(event)`, `list_events(limit, before=None)`, `append_load_point(point)`, `list_load_points(since)` | 🆕 |

Quy ước:

- Vào và ra đều là model Pydantic của `src/models/`; không lớp ORM nào lọt ra ngoài `repository`.
- Mỗi hàm là một giao dịch. Việc cần nguyên tử thì gộp vào một hàm (`save_booking` ghi booking và khoá idempotency
  cùng lúc).
- Không tìm thấy thì trả `None` hoặc danh sách rỗng; không ném lỗi.
- `find_idempotent` ném `DomainError("idempotency_mismatch")` khi cùng key nhưng khác `request_hash`.

## 6. Luồng dữ liệu

```mermaid
flowchart LR
    API["src/api (router)"] --> SVC["src/services/*"]
    AG["src/agents/tools"] --> SVC
    GD["src/guard (sinks)"] --> REPO
    SVC --> REPO["services/repository.py<br/>Pydantic vào / ra"]
    REPO --> MAP["db/mappers.py"]
    MAP --> ORM["db/tables.py"]
    ORM --> ENG["db/session.py — engine"]
    ENG --> SQLITE[("SQLite<br/>data/app.db")]
    ENG --> NEON[("Neon Postgres")]
    MIG["migrations/ (Alembic)"] --> ENG
```

## 7. Migration và seed

- Mỗi thay đổi schema là **một revision Alembic trong cùng PR** với thay đổi ở `tables.py`. Sinh bằng `--autogenerate`
  rồi đọc lại bằng mắt. Không sửa revision đã chạy trên Neon.
- Tên file: `NNNN_mo_ta.py`, đánh số tăng dần.
- Thay đổi phá vỡ (xoá / đổi tên cột) làm hai bước: thêm mới → chuyển dữ liệu → xoá ở revision sau.
- `tests/test_db/test_migrations.py`: chạy `alembic upgrade head` trên SQLite trống rồi so với `Base.metadata`; lệch là
  quên viết migration.
- Deploy: container chạy `alembic upgrade head` **trước** `uvicorn`. Migration lỗi thì health check không qua và Render
  giữ bản cũ. Cách này không cần shell hay lệnh pre-deploy của gói trả phí.
- Máy local: xoá `data/app.db` để làm lại từ đầu.
- Seed tài khoản: `auth.ensure_seed_users()` chạy trong lifespan, đọc biến môi trường `SEED_USERS_JSON` (danh sách
  `email, password, role, display_name, vehicle_model`), `upsert` theo email. Không có tài khoản hay mật khẩu nào
  trong repo. Thiếu biến thì không seed và ghi log cảnh báo.
- Không seed booking. Dữ liệu demo sinh ra từ kịch bản mô phỏng.

## 8. Riêng tư (NFR)

- Mọi bảng nghiệp vụ dùng `user_id` giả danh; email chỉ ở `users`.
- "Cho phép sửa / xoá thông tin" (Q9): `PUT /resident/profile` sửa; `DELETE /resident/profile` gọi `anonymize_user`:
  email đổi thành giá trị vô nghĩa, xoá `password_hash`, đặt `deleted_at`, huỷ booking đang hiệu lực. Booking cũ và
  nhật ký quyết định giữ lại dưới mã giả danh để FR14 còn nguyên vẹn.
- Trace LangSmith và log ứng dụng chỉ chứa `user_id`.

## 9. Map FR/AC → bảng → test

| Yêu cầu | Bảng / hàm | Test (＋ = thêm ở Pha B; `skip [T1.6]` khi chưa có logic) |
|---|---|---|
| FR1 | `users` · `get_user_by_email`, `upsert_user` | ＋ `test_repository.py::test_user_roundtrip` |
| FR2, FR8 | `bookings` · `save_booking`, `list_bookings` | ＋ `test_booking_roundtrip_keeps_timezone` |
| Idempotency | `idempotency_keys` · `find_idempotent` | ＋ `test_same_key_same_booking`, `test_same_key_other_body_conflicts` |
| FR13, AC4 | `approvals` · `overdue_approvals` | ＋ `test_overdue_approvals_are_listed` |
| FR14 | `decision_log` · `append_decision` | ＋ `test_decision_log_is_append_only`, `test_blocked_only_filter` |
| FR15 | `notifications` | ＋ `test_notifications_are_per_resident` |
| FR16 | `load_points`, `station_events` | ＋ `test_load_points_window` |
| NFR khả dụng | `schedule_plans` · `latest_plan` | ＋ `test_latest_plan_survives_restart` |
| NFR riêng tư | `anonymize_user` | ＋ `test_anonymize_removes_email_keeps_log` |
| AI-1 / HITL (21/11) | `proposals`, `consents`, `vehicle_revisions`, `audit_log` (§0) | chưa có — cần test: stale, duyệt hai lần, sai chủ sở hữu, re-verify trước apply |
| Ranh giới | — | ＋ `test_architecture.py::test_only_repository_touches_orm` |
| Migration | `migrations/` | ＋ `test_migrations.py::test_head_matches_metadata` |

## 10. Rủi ro

| Rủi ro | Giảm thiểu |
|---|---|
| Hành vi SQLite khác Postgres (múi giờ, JSON, khoá) | `UtcDateTime`; không truy vấn trong JSON; job Postgres trong CI |
| Cột khoá lệch `payload` | Chỉ `mappers.py` ghi; test round-trip từng bảng |
| Neon vừa thức dậy làm request đầu chậm | `pool_pre_ping`; frontend đã retry 503 (20 §7) |
| Gói free giới hạn dung lượng | Cắt `schedule_plans` còn 200 bản, chuỗi thời gian 7 ngày; benchmark không ghi DB |
| Migration hỏng lúc deploy | Chạy `alembic upgrade head` trong job `docker-smoke` trước khi Render deploy |
| Hai request đặt lịch đồng thời | Khoá idempotency là PK; index duy nhất một phần cho booking hiệu lực |

## 11. Thứ tự làm trong Pha B và Definition of Done

1. Sau khi D1 / D2 được duyệt: thêm dependency vào `requirements.txt` kèm lý do + task.
2. `src/db/base.py`, `types.py`, `tables.py`, `session.py`, `mappers.py` (mapper là stub `[T1.6]`).
3. `alembic.ini`, `migrations/env.py`, `versions/0001_initial.py` (sinh từ `tables.py`).
4. `models/identity.py`; thêm stub mới vào `repository.py`.
5. Luật ranh giới ORM trong `test_architecture.py`; `test_migrations.py` chạy thật; `test_repository.py` ở dạng `skip`.

DoD: 4 lệnh quy tắc 10 xanh; `alembic upgrade head` chạy được trên SQLite trống; `src/models/` không import
`sqlalchemy`; ngoài `src/db/` và `repository.py` không file nào import ORM; app vẫn khởi động khi chưa có DB.
