# Prompts — external file pattern (C2)

Thư mục này chứa prompt dưới dạng `.md` file tách khỏi code (inspire team 004 —
`prompts/*.md` với `{{placeholder}}`). Lợi ích:

- Đổi prompt KHÔNG cần sửa code / deploy lại.
- Copywriter / mentor review được prompt mà không cần đọc Python.
- Diff history rõ ràng trên git.

## Cấu trúc

Prompt của ChargePilot (Agent F1 — `docs/plan/30-ai.md` §3.7):

- `reason.md` — prompt của node `reason`: chọn tool hay trả lời. Biến: danh sách tool + tham số, bối cảnh lượt
  chat do server cấp (`now`, `timezone`, xe của cư dân), `draft_request`, lịch sử.
- `finalize.md` — prompt của node `finalize`: diễn đạt lại dữ kiện do code tính, không tự tính số.
- `charging_domain.md` — kiến thức miền và quy tắc trích `ChargeRequest` (thiếu trường thì hỏi lại, không đoán).
- `charging_safeguards.md` — quy tắc an toàn của ChargePilot (không ra lệnh trạm, không tiết lộ dữ liệu cư dân khác).

Prompt của template (pipeline RAG mẫu — giữ tới T2.5 rồi gỡ):

- `system_prompt.md` — system prompt đầy đủ, XML tags (`<role>` / `<context>` /
  `<instructions>` / `<rules>` / `<safeguards>` / `<output_format>` /
  `<verification>`). Inspire team 002, 004, 007.
- `safeguards.md` — quy tắc an toàn tách bạch khỏi personality (inspire team 005).
- `citation_rules.md` — contract citation với frontend (inspire team 006).

## Placeholder

Dùng `{{tên_biến}}` — `src/llm_chat/prompts.py` sẽ substitute. Ví dụ:
`{{shared_rules}}`, `{{safeguards}}`.

`render(name, **variables)` thay biến **một lượt** và **fail khi thiếu biến** — nội dung người dùng chèn vào không
thể kéo thêm placeholder khác vào prompt. `tests/test_agents/test_charging_agent.py` kiểm cả hai điều này, và kiểm
rằng không có prompt dài nào nhúng trong module node.

## Loader

```python
from src.llm_chat.prompts import load_prompt, render, SHARED_RULES

text = render("finalize.md", **variables)  # ChargePilot: thiếu biến → lỗi ngay

# Template (pipeline RAG):

prompt = load_prompt("system_prompt.md").format(
    shared_rules=SHARED_RULES,
    safeguards=load_prompt("safeguards.md"),
)
```

Loader cache (`@lru_cache`) để không đọc disk nhiều lần (inspire team 003).
