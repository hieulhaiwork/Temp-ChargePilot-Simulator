"""Safety Guard (F4) — trụ 3 của nguyên tắc: "Bộ kiểm tra an toàn kiểm soát thực thi".

KHÁC với src/agents/guardrails.py: guardrails.py chặn prompt injection / output bịa của
LLM; package này kiểm LỆNH ĐIỀU KHIỂN trạm. Hai lớp độc lập (defence-in-depth).

Bất biến (PRD F4, NFR an toàn — khoá bởi tests/test_architecture.py):
  - Code XÁC ĐỊNH, không import agents/LLM: bảo vệ khẩn cấp phải chạy kể cả khi LLM sập.
  - dispatcher.py là chokepoint DUY NHẤT tới simulator (StationActuator.apply_commands).
  - 100% lệnh qua checker; lệnh vi phạm bị chặn, ghi log, hiện ở S7, KHÔNG tới simulator (AC6).

    rules.py       7 luật FR12 (mỗi luật một hàm thuần + một unit test)
    checker.py     chạy mọi luật → GuardVerdict
    approval.py    phân loại + vòng đời phê duyệt (FR13, AC4)
    emergency.py   bảo vệ khẩn cấp khi nguồn giảm (FR13 dòng 2, AC5)
    dispatcher.py  luồng check → duyệt → apply → nhật ký (FR14)

Owner: TV3. Task: T3.1 (luật), T3.2 (phê duyệt, khẩn cấp, dispatcher).
"""
