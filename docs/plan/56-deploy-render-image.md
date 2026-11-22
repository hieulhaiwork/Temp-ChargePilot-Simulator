# Plan 56 — Deploy backend lên Render bằng Docker image (không cần GitHub App)

> Trạng thái: **bản test đã chạy thật 2026-11-22** (Render + Vercel + Neon). Production chưa dựng.
> Liên quan: [50-devops.md](50-devops.md), [55-ci-runner.md](55-ci-runner.md). Job CI: `deploy` trong
> `.github/workflows/ci.yml`.

## 0. Hiện trạng (cập nhật 2026-11-22)

| Thành phần | Ở đâu | Trạng thái |
|---|---|---|
| Web (frontend) | **https://p019-web.vercel.app** — Vercel, project `p019-web`, team *SWP391's projects* | ✅ Ready. Đang trỏ backend **bản test** |
| Backend bản test | **https://p019-backend-develop.onrender.com** — Render, service `p019-backend:develop`, gói Free | ✅ Live: `/health`, `/ready` (DB ok), CORS, đăng nhập, WebSocket đã kiểm |
| Database bản test | Neon, project `p019`, nhánh `dev` | ✅ Migration `0001` đã chạy |
| Image | Docker Hub `docker.io/minhmama/p019-backend` (private), tag `develop` + `<commit>` | ✅ CI push tự động khi merge vào `develop` |
| CI | GitHub Actions, runner `team-19` (hiện là VM trên laptop — [plan 55](55-ci-runner.md)) | ✅ 6 job xanh trên `develop` |
| Backend production | Render service mới theo `main`, Neon nhánh `main` | ⏳ Chưa dựng (§3.5) |

Còn thiếu để bản test tự cập nhật khi merge:

- [ ] Secret GitHub `RENDER_DEPLOY_HOOK_TEST` (Render → service → Settings → Deploy Hook).
- [ ] Render → Environment: `CORS_ORIGINS` thêm `https://p019-web.vercel.app`.
- [ ] (Tuỳ chọn) Vercel → Settings: Node.js Version **22.x**, Functions Region **sin1**; Render: đổi tên service thành
  `p019-backend-test` (URL giữ nguyên).

### Ai giữ quyền gì

| Tài khoản | Giữ | Thành viên khác cần gì |
|---|---|---|
| GitHub repo (BTC) | Code, CI, Variables/Secrets | Quyền ghi repo (đã có) — mọi người đều sửa được secret |
| Docker Hub `minhmama` | Repo image + 2 token | Không cần: CI và Render dùng token |
| Render | 2 service backend | Muốn xem log / sửa biến: chủ workspace mời qua *Invite your team* |
| Neon | Project `p019` | Muốn chạy SQL: chủ project mời vào project |
| Vercel | Project `p019-web` | Muốn tự deploy web: được mời vào team *SWP391's projects* (hoặc nhờ người có quyền chạy lệnh §5) |

Secret (key OpenAI, chuỗi Neon, `JWT_SECRET`, mật khẩu tài khoản demo, Deploy Hook, token Docker Hub) **không ghi
trong repo, không gửi qua chat** — hỏi người giữ tài khoản tương ứng.

## 1. Vì sao không deploy thẳng từ repo

Org `AI20K-Build-Phase-Cohort-5` tắt cài GitHub App ("Installations and requests are disabled"), nên Render không đọc
được repo private `P-019`: Blueprint (`render.yaml`, `render.test.yaml`) và "Auto-Deploy after CI checks pass" không
dùng được. Render vẫn chạy được **image dựng sẵn** (*Existing Image*), không cần quyền gì trên repo.

```
merge vào develop/main → CI 5 job xanh → job deploy (VM runner):
    docker build → push docker.io/<user>/p019-backend:<commit> → gọi Render Deploy Hook (imgURL = đúng tag đó)
Render: kéo image → `alembic upgrade head` → uvicorn 1 worker → healthcheck /health → Live
```

`render.yaml` / `render.test.yaml` giữ lại làm **danh sách biến môi trường chuẩn**; khi BTC cài được Render GitHub App
thì chuyển service về Blueprint, bỏ job `deploy`.

## 2. RAM trên gói free (512 MB)

Đo 2026-11-22 (Windows, `.venv` cùng gói với image, 1 worker): rảnh sau khởi động ~171 MB; cao nhất **~191 MB** sau
smoke đủ luồng (đăng nhập 2 vai trò, quote, booking idempotent, sự cố nguồn, 1 lần mô phỏng `hybrid_evening` B,
WebSocket). Chưa đo `/chat` với LLM thật. → Đủ cho gói free; theo dõi tab **Metrics** của Render sau lần deploy đầu.

## 3. Cài đặt một lần

### 3.1 Docker Hub (chủ repo image làm)

1. Tạo tài khoản Docker Hub (đăng ký bằng email, không cần GitHub).
2. **Create repository** `p019-backend`, Visibility **Private** (gói free có 1 repo private).
3. Account Settings → Personal access tokens → tạo **hai** token:
   - `p019-ci-push` — quyền **Read & Write** (cho CI push).
   - `p019-render-pull` — quyền **Read-only** (cho Render kéo image).

### 3.2 GitHub — Settings → Secrets and variables → Actions

| Loại | Tên | Giá trị |
|---|---|---|
| Variable | `DOCKERHUB_IMAGE` | `docker.io/<user>/p019-backend` |
| Secret | `DOCKERHUB_USERNAME` | tên tài khoản Docker Hub |
| Secret | `DOCKERHUB_TOKEN` | token `p019-ci-push` |
| Secret | `RENDER_DEPLOY_HOOK_TEST` | thêm ở bước 3.4 |
| Secret | `RENDER_DEPLOY_HOOK_PROD` | thêm khi tạo bản production |

Thiếu biến nào thì job `deploy` chỉ cảnh báo và bỏ qua, CI không đỏ.

### 3.3 Image đầu tiên

Render cần có image trước khi tạo service. Sau khi PR thêm job `deploy` vào `develop`, lần CI đầu tiên trên `develop`
(VM runner phải bật) sẽ push `…/p019-backend:develop` và `…:<commit>`. Kiểm tra trên Docker Hub → Tags.

### 3.4 Render — service bản test

1. New → **Web Service** → **Existing Image**.
2. Image URL: `docker.io/<user>/p019-backend:develop`. **Credential**: thêm Registry Credential loại Docker Hub —
   username + token `p019-render-pull`.
3. Name `p019-backend-test`, Region **Singapore**, Instance **Free**.
4. Advanced → **Health Check Path** `/health`. Không đặt Start Command (dùng `CMD` của Dockerfile: migration rồi
   uvicorn, đọc cổng từ `PORT` do Render cấp).
5. Environment — đặt theo bảng §4.
6. Create → chờ Live. Logs phải có `Context impl PostgresqlImpl.` và `Running upgrade  -> 0001`.
7. Settings → **Deploy Hook** → copy URL → lưu vào GitHub secret `RENDER_DEPLOY_HOOK_TEST`. URL này là bí mật (ai có
   nó đều kích deploy được).

Ghi chú khi làm thật (2026-11-22):

- Ô Image URL dùng dấu **hai chấm** trước tag (`…/p019-backend:develop`, không phải `.develop`).
- Render báo "image URL and registry credential are invalid" khi **tag chưa tồn tại** — đợi job `deploy` push xong
  (xem tab Tags trên Docker Hub) rồi chọn lại credential.
- **Region không đổi được** sau khi tạo: chọn trùng vùng của Neon (host chuỗi kết nối, ví dụ `ap-southeast-1` =
  Singapore).
- `JWT_SECRET`: để trống ô value rồi bấm **Generate** của Render — không tạo trong khung chat AI (lộ vào log).
- Log `HEAD / 404` ngay sau khi chạy là Render dò cổng, không phải lỗi.

### 3.5 Bản production

Làm giống hệt khi `main` đã có code: image `…:main`, name `p019-backend`, Neon nhánh `main`, `JWT_SECRET` khác,
hook → `RENDER_DEPLOY_HOOK_PROD`, `CORS_ORIGINS` = đúng domain web production (không đặt `CORS_ORIGIN_REGEX`).
Gói: Free khi phát triển; nâng **Starter** (0,5 CPU, không ngủ) trước demo — Settings → Instance Type, đổi được bất cứ
lúc nào (service khởi động lại một lần). Sau đó đổi `NEXT_PUBLIC_API_URL` môi trường Production của Vercel sang URL
production và `vercel deploy --prod`.

## 4. Biến môi trường trên Render

Tên biến phải **đúng như code đọc** (`src/config.py`). Lưu ý: hướng dẫn chung của BTC dùng `ENVIRONMENT` /
`LANGSMITH_*` — code dự án **không đọc** `ENVIRONMENT`.

| Biến | Bản test | Production | Ghi chú |
|---|---|---|---|
| `APP_ENV` | `production` | `production` | Bật kiểm tra secret khi khởi động |
| `LOG_LEVEL` | `INFO` | `INFO` | |
| `OPENAI_API_KEY` | key thật | key thật | Bắt buộc khi `APP_ENV=production`. Đặt hạn mức chi tiêu ở OpenAI |
| `DATABASE_URL` | Neon **dev** | Neon **prod** | Chuỗi direct `postgresql://…?sslmode=require`. Trống = SQLite tạm, mất dữ liệu khi restart |
| `JWT_SECRET` | chuỗi ngẫu nhiên ≥ 32 ký tự | chuỗi **khác** | `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `SEED_USERS_JSON` | JSON một dòng | JSON một dòng | Xem `.env.example`; `vehicle_model` phải có trong `config/vehicles.yaml` |
| `CORS_ORIGINS` | domain web test | domain web production | `https://…`, không có `/` cuối, cách nhau dấu phẩy |
| `CORS_ORIGIN_REGEX` | `^https://.*\.vercel\.app$` | (không đặt) | Chỉ bản test, cho URL preview |
| `CONTROL_LOOP_ENABLED` | `true` | `true` | ADR-007 — trạm tự chạy theo thời gian. Gói Free ngủ thì vòng nền dừng: production cần Starter |
| `LANGCHAIN_TRACING_V2` | `true` nếu có key, không thì `false` | như bản test | |
| `LANGCHAIN_API_KEY` | key LangSmith | key LangSmith | |
| `LANGCHAIN_PROJECT` | `p019-test` | `p019` | |

## 5. Frontend (Vercel) — cũng không cần GitHub App

Vercel nối repo cũng cần GitHub App (đã thử: "Failed to connect … to project"), nên deploy bằng CLI từ máy.
Project đã có: `p019-web` trong team *SWP391's projects*; biến `NEXT_PUBLIC_API_URL` (Preview + Production) =
`https://p019-backend-develop.onrender.com`.

Người mới deploy lần đầu trên máy mình (cần được mời vào team Vercel):

```bash
cd frontend
npx vercel login
npx vercel link --yes --project p019-web --scope swp391s-projects-ae5ca460
```

Mỗi lần web thay đổi (chạy từ `develop` / `main` mới nhất, working tree sạch):

```bash
cd frontend
npx vercel deploy          # bản preview — URL riêng, cần đăng nhập Vercel mới xem (Deployment Protection)
npx vercel deploy --prod   # cập nhật https://p019-web.vercel.app
```

- `NEXT_PUBLIC_*` được gắn vào bundle lúc build: đổi biến (`npx vercel env …` hoặc dashboard) thì phải deploy lại.
- `vercel link` tạo `frontend/.vercel/` và `frontend/.env.local` (token tạm của Vercel) — cả hai đã bị `.gitignore`,
  không commit.
- Web **không** tự deploy khi merge (khác backend).
- Domain web phải có trong `CORS_ORIGINS` của backend tương ứng.

## 6. Kiểm tra sau mỗi lần deploy

Bản test: `<service>` = `p019-backend-develop`, `<web>` = `p019-web`. Gói Free ngủ sau 15 phút không có request —
lần gọi đầu chờ ~50 giây là bình thường.

```bash
curl https://<service>.onrender.com/health   # {"status":"ok","env":"production"}
curl https://<service>.onrender.com/ready    # {"status":"ok","checks":{"config":"ok","database":"ok"}}
curl -i -X OPTIONS https://<service>.onrender.com/api/v1/auth/login \
  -H "Origin: https://<web>.vercel.app" -H "Access-Control-Request-Method: POST"   # có access-control-allow-origin
```

Rồi đăng nhập bằng tài khoản seed trên web, mở màn vận hành: WebSocket phải ở trạng thái "Trực tiếp".

## 7. An toàn

- Secret của repo dùng được trong workflow của **mọi PR mở từ nhánh trong repo** (không phải fork). Job `deploy` chỉ
  chạy khi push vào `develop` / `main`, nhưng người có quyền push vẫn có thể sửa workflow trong PR để đọc secret —
  chỉ thành viên nhóm có quyền ghi, chấp nhận được; token Docker Hub và Deploy Hook có thể thu hồi và tạo lại bất kỳ lúc nào.
- Job `deploy` `docker logout` và xoá image sau mỗi lần chạy (runner dùng chung).
- Không commit hook URL, token hay `.env`.
