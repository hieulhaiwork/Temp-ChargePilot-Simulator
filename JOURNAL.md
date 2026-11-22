# Weekly Journal — Team T019 (ChargePilot, SC-16)

> Ghi lại mỗi tuần: học được gì, khó khăn gì, quyết định gì, kế hoạch tiếp.
> Nguồn: lịch sử commit / PR trên GitHub, `docs/plan/`, `docs/adr/`, `eval/evidence/`. Phần repo không ghi nhận
> được để `[nhóm bổ sung]`.

---

## Week 1: 05/11/2026 – 11/11/2026

### Mục tiêu tuần này
- [x] Nhận đề SC-16 và repo của đội (tạo từ AI20K Agent Template ngày 05/11)
- [ ] [nhóm bổ sung]

### Đã hoàn thành
- Repo `P-019` được tạo từ template (commit đầu ngày 05/11).
- [nhóm bổ sung — tuần này chưa có commit hay tài liệu nào trong repo]

### Khó khăn & Giải pháp
| Khó khăn | Giải pháp | Kết quả |
|----------|-----------|---------|
| [nhóm bổ sung] | | |

### Bài học
- [nhóm bổ sung]

### Kế hoạch tuần sau
- [x] Lập plan chi tiết backend / frontend / AI / database / DevOps
- [x] Dựng skeleton chạy được để chia việc song song

---

## Week 2: 12/11/2026 – 18/11/2026

### Mục tiêu tuần này
- [x] Pha A — plan chi tiết cho 5 mảng (`docs/plan/00…50`) và các ADR nền (ADR-001…009)
- [x] Pha B — skeleton **contract-first**: app khởi động được, `/docs` đủ endpoint, việc chưa làm trả 501 kèm mã task
- [x] CI chạy được dù org không cấp phút GitHub-hosted
- [x] Đặc tả UI và mockup để làm giao diện song song

### Đã hoàn thành
- Plan Pha A (16/11) và skeleton ChargePilot: 3 trụ Agent / Optimizer / Guard, 9 bảng DB + Alembic, router REST +
  WebSocket, Next.js 13 route, Docker, test kiến trúc khoá ranh giới import (17/11).
- CI 4 job (backend, backend-postgres, frontend, docker-smoke) trên **self-hosted runner** `team-19` trong VM
  VirtualBox; hướng dẫn dựng runner cho từng thành viên (`docs/plan/55-ci-runner.md`).
- Đặc tả UI 11 màn S1–S8 (`docs/plan/21-ui-spec.md`), mockup HTML 11 màn + design system + plugin Figma sinh từ DOM,
  plan chia việc UI 2 người × 2 ngày.
- Màn vận hành desktop được mở rộng (18/11).

### Khó khăn & Giải pháp
| Khó khăn | Giải pháp | Kết quả |
|----------|-----------|---------|
| Org không cấp phút GitHub Actions cho repo private | Self-hosted runner nhãn `team-19` trong VM, mỗi người tự dựng được | CI chạy, job tự đi sang máy nào đang bật |
| `npm ci` trên CI lỗi vì lockfile sinh bằng Node 26 / npm 11 | Sinh lại `package-lock.json` bằng Node 22 (`frontend/.nvmrc`) | Job frontend xanh |
| Sơ đồ Mermaid sequence hỏng vì alias `OPT` trùng từ khoá `opt` | Đổi alias, thêm bước parse thử mọi khối Mermaid | 26 khối, 0 lỗi |
| Nhiều người làm song song khi logic chưa có | Skeleton contract-first: stub `NotImplementedError("[Txx]")` → 501 | Web và API làm song song trên hợp đồng chung |

### Bài học
- Khoá hợp đồng (Pydantic model, OpenAPI → type TypeScript) trước giúp chia việc mà không chặn nhau.
- Ranh giới kiến trúc phải được **test** (`tests/test_architecture.py`), chỉ ghi trong tài liệu thì sẽ trôi.

### Kế hoạch tuần sau
- [x] Simulator thật thay cho stub; quyết định bãi AC / DC
- [x] Hoàn thiện backend: DB, auth, Guard, optimizer, vòng điều khiển
- [x] Deploy bản chạy được (Integration Gate 1, 22/11)

---

## Week 3: 19/11/2026 – 25/11/2026 (ghi tới 22/11)

### Mục tiêu tuần này
- [x] Căn chỉnh theo hướng nghiên cứu SC-16 mới: bãi hybrid AC + DC (ADR-010…015, PRD v0.4)
- [x] Simulator R&D v1.2 và optimizer AC / DC (MVP-2 / MVP-3)
- [x] Backend chạy thật từ đầu tới cuối, Agent chat streaming
- [x] Deploy bản test: web + API + database có URL thật
- [ ] Release Candidate 26/11: production, AI-4 WHY / WHAT-IF, video + pitch deck

### Đã hoàn thành
- **Simulator R&D** (`src/simulator/src/`): `HybridSimulator` EV2Gym-first, AC native + DC extension theo profile VinFast,
  kiến trúc AC/DC module hoá, bộ test 163 case gồm golden regression; optimizer DC và AC / Global Optimizer MVP-2 / 3
  (PR #7, 19–21/11).
- **Nghiên cứu / thiết kế**: ADR-010…015, PRD v0.4, business overview, thiết kế trả lời 3 tầng; topology chuyển sang
  fixture `mvp1` (2 cổng AC 11 kW + 2 cổng DC 60 kW, lưới 106 kW) (PR #5, 21/11). Nhánh R&D thử nghiệm AI-1…AI-4.
- **Frontend**: giao diện theo template mockup, màn vận hành cho bãi AC / DC, sơ đồ bãi (SiteMap) (PR #4, 19–21/11).
- **Agent F1**: chat streaming SSE, gợi ý trả lời nhanh, prompt bãi hybrid (PR #6, 21/11).
- **Backend chạy thật** (PR #8, 22/11): repository + auth JWT, Guard 7 luật + phê duyệt + bảo vệ khẩn cấp, optimizer
  FCFS / EDF / LP HiGHS / MPC, `LiveStation`, vòng điều khiển, WebSocket; 405 test.
- **Deploy** (PR #9, #10, 22/11): CI build image → Docker Hub → Render Deploy Hook; web qua Vercel CLI; Neon. Bản test
  chạy tại <https://p019-web.vercel.app>.
- **Benchmark A–D** có bằng chứng chạy lại được (`eval/evidence/2026-11-22/`): 0 lần vượt giới hạn nguồn; B rẻ hơn
  EDF 12–14% nhưng không đúng hạn hơn.
- Sửa lỗi LP bỏ qua mức đồng ý lùi giờ của cư dân; bật vòng nền để trạm tự vận hành (nhánh `fix/booking-charging-state`).
- Hook ghi log AI cho Antigravity, pre-push gửi log (19–21/11).

### Khó khăn & Giải pháp
| Khó khăn | Giải pháp | Kết quả |
|----------|-----------|---------|
| `HybridSimulator` tự dispatch + guard riêng, chạy trọn kịch bản, cần ev2gym → không đặt sau Guard của backend được | ADR-016: `LiveStation` cho backend; `HybridSimulator` giữ cho R&D offline; không trộn số liệu | Pipeline Optimizer → Guard → trạm chạy đầu-cuối |
| HiGHS segfault khi LP chạy trên thread khác nhau | Gom mọi lần giải LP về một worker thread (`services/solver.py`) | Benchmark 50 lần chạy, 0 lỗi |
| Org chặn cài GitHub App → Render / Vercel không đọc được repo | Backend deploy bằng Docker image (Docker Hub + Deploy Hook), web bằng Vercel CLI | Bản test live, merge `develop` là tự deploy backend |
| VM runner treo lúc boot (Hyper-V), lỗi mạng tạm làm job bị huỷ | Reset VM, `gh run rerun --failed`, timeout tải cache 2 phút, nới timeout job | CI xanh 6 / 6 trên `develop` |
| Job CI simulator không import được `src` | `pythonpath = .` trong `pytest.ini` | 163 test simulator xanh trên CI |
| Chat trên Render đứt im lặng | Đọc log Render: `OPENAI_API_KEY` còn chuỗi mẫu tiếng Việt → lỗi header ASCII | Thay key thật; ghi bẫy vào HANDOFF |
| Xe walk-in cắm cổng nhưng 0 kW hàng giờ | LP thêm ràng buộc mềm "phải bắt đầu trong thời hạn cư dân cho lùi" | Walk-in sạc ngay; benchmark không đổi |

### Bài học
- **Code là nguồn sự thật**: tài liệu trôi rất nhanh (bãi 8 × 7 kW, "backend chạy HybridSimulator"…) → rà tài liệu
  theo code trước mỗi mốc.
- Chỉ tuyên bố điều có bằng chứng: B tiết kiệm tiền nhưng **không** đúng hạn hơn baseline — báo cả thắng, hoà, thua.
- Secret (key, chuỗi kết nối, JWT) không đi qua khung chat AI — hook ghi log gửi prompt lên server.
- Tách quyết định "vượt quyền" cho người, còn lại để hệ thống tự vận hành; mức đồng ý của cư dân phải đi vào
  ràng buộc của bộ tối ưu, không chỉ ở bước phê duyệt.

### Kế hoạch tuần sau (tới Release Candidate 26/11)
- [ ] Merge `fix/booking-charging-state`; bật `CONTROL_LOOP_ENABLED` trên Render
- [ ] Chốt chính sách tạm dừng sạc khi cư dân cho phép giảm công suất
- [ ] Dựng production (Render Starter, Neon `main`, Vercel production)
- [ ] AI-4 WHY / WHAT-IF; giới hạn tần suất chat
- [ ] Video demo ≤ 5 phút và pitch deck 10 slide
