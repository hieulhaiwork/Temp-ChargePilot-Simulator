# Demo Chat Agent cho cư dân và vận hành

Fixture dùng SQLite tạm, dữ liệu tổng hợp, provider có kịch bản và engine thật. Tài khoản fixture dùng miền `g6a.example` và mật khẩu `fixture-only-passphrase`. Mở hai terminal từ gốc repo.

```bash
CORS_ORIGINS=http://127.0.0.1:3019 .simulator/bin/python eval/evidence/2026-11-26-ai4-g6b/run_demo.py --port 8019
```

```bash
cd frontend
NEXT_PUBLIC_API_URL=http://127.0.0.1:8019 npm run build -- --webpack
npm run start -- --hostname 127.0.0.1 --port 3019
```

Mở `http://127.0.0.1:3019/login` và dùng ô Trợ lý sạc.

| Tài khoản | Câu hỏi fixture |
|---|---|
| `res-resident-demo@g6a.example` | Vì sao xe tôi đang chờ? |
| Cư dân | Xem xe tôi xoay xở ra sao với mục tiêu 75%. |
| Cư dân | Tôi cần đi sau 70 phút, thử mức từ 65% đến 75%. Vì sao xe tôi đang chờ và có phương án nào tốt hơn không? Tôi đồng ý giảm mục tiêu. Tôi đồng ý mất cam kết gốc. Giữ nguyên hoặc rút ngắn hạn. |
| `operator@g6a.example` | Vì sao các xe bị trễ? |
| Vận hành | Xem bãi xoay xở thế nào với nguồn 50 kW, dùng bản sao mô phỏng. |
| Vận hành | Vì sao các xe bị trễ và cần nguồn điện bao nhiêu để đáp ứng các cam kết? Thử 22 đến 106 kW, giữ các xe AC đúng hạn. |

Chờ job đầu hoàn tất và đủ 15 giây từ lần nộp trước để thử một mô phỏng khác cùng tài khoản. Thu gọn và mở bảng bằng chứng để xem cam kết, hạn, mốc đạt mức pin và mốc nhả cổng. Các booking tải cao có thể không có lựa chọn khả thi. Thử đổi sang `second-resident@g6a.example` trong cùng tab để kiểm cô lập.

Chromium smoke dùng Playwright cài ở một thư mục tạm, cùng frontend và API đang chạy. Script in kết quả đã lọc theo quyền và phiên bản Chromium.

```bash
node eval/evidence/2026-11-26-ai4-g6b/browser_smoke.mjs /tmp/p019-g6b-browser http://127.0.0.1:3019
```

Oracle M3a/M3b tái lập qua `pytest tests/test_services/test_recommendation_hybrid.py tests/test_api/test_unified_copilot.py`. Hai case nhiều công cụ ghi dữ liệu engine thật trong JUnit. Xem cả chế độ provider, runner kiểm tra và giới hạn nghiệm thu trong báo cáo pha. [Báo cáo G6B](PHASE_4_4B_REPORT.md)
