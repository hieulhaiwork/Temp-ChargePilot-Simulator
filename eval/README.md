# Evaluation Framework (C3)

Thư mục này có HAI bộ đánh giá:

1. **Của ChargePilot** (mục "ChargePilot — đánh giá riêng của đề tài" bên dưới): eval Agent F1 trên câu yêu cầu
   sạc có nhãn, và benchmark A–D của bộ tối ưu. Đây là bằng chứng cho PRD §8.
2. **Của template** (`run_eval.py`, `judge.py`, `golden_dataset.yaml`): eval pipeline RAG mẫu (inspire team 008
   Buddy + 009 VibeMaster + 011 CareerPulse). Giữ tới T2.5 rồi gỡ cùng phần RAG.

## Files

| File | Vai trò |
|---|---|
| `golden_dataset.yaml` | Dataset 10 cases (happy / ambiguous / safety / citation / injection / robustness) |
| `run_eval.py` | Runner — chạy agent trên mỗi case, auto-check deterministic |
| `judge.py` | LLM-as-Judge — chấm faithfulness/helpfulness/safety/citation (1-5) |
| `cost_benchmark.py` | Ước chi phí chạy eval trên các model |
| `thresholds.yaml` | Gate: pass_rate ≥ 80%, judge avg ≥ 4.0, safety 0 fail |
| `results/<ts>/` | Output mỗi đợt: report.md + cases.json + judge_input.jsonl |

## Chạy

```bash
# 1. Cài pyyaml
pip install pyyaml

# 2. Chạy eval offline (không gọi LLM): OPENAI_API_KEY phải RỖNG, và ghi kết quả ra thư mục tạm
#    (mặc định script ghi đè eval/results/report.md — file được track)
OPENAI_API_KEY="" python eval/run_eval.py --out /tmp/p019-eval

# 3. (optional) LLM-as-Judge — cần OPENAI_API_KEY
python eval/judge.py eval/results/<ts>/judge_input.jsonl

# 4. Ước chi phí
python eval/cost_benchmark.py
```

## ChargePilot — đánh giá riêng của đề tài

| File | Vai trò | Task |
|---|---|---|
| `run_agent_eval.py` | Eval Agent F1. `--offline`: kiểm dataset (schema, id trùng, nhãn, độ phủ nhóm) + khối `charging:` của `thresholds.yaml`, không gọi LLM, chạy được trong CI. Mặc định (chạy Agent thật rồi chấm): chưa làm, exit 2 | T4.2 |
| `datasets/charging_requests.jsonl` | Câu yêu cầu sạc có nhãn cho F1 (trích xuất / hỏi lại / phương án thay thế / từ chối / injection) — hiện 25 câu, PRD cần ≥ 50 | T4.2 |
| `thresholds.yaml` → `charging:` | Ngưỡng đề xuất: đúng từng trường ≥ 0.90, đúng cả yêu cầu ≥ 0.80, đúng thao tác ≥ 0.90, hỏi lại khi thiếu ≥ 0.95, an toàn 0 lỗi, kWh từ code = 1.0. Chốt lại sau lần chạy thật đầu tiên | T4.2 |
| `run_benchmark.py` | Benchmark A–D (FCFS/EDF, tối ưu không ML, tối ưu + ML, oracle) trên cùng kịch bản `config/scenarios/`, nhiều seed (`--seeds`) → `results/benchmark.md` + `results/benchmark.json` (file JSON này được đưa vào image cho `GET /simulation/benchmark`) | T3.4 |

```bash
make eval-agent           # = python eval/run_agent_eval.py --offline
make benchmark            # = python eval/run_benchmark.py (exit 2 khi pipeline còn stub)
```

Định nghĩa KPI dùng chung cho S8 và báo cáo ở `src/simulator/kpi.py`. Nguyên tắc PRD §8:
nếu C không tốt hơn B thì KHÔNG tuyên bố AI cải thiện tối ưu.

> `run_eval.py` coi mọi `OPENAI_API_KEY` khác rỗng là key thật. Nếu `.env` còn chuỗi placeholder,
> eval chạy chế độ "LLM thật" và fail 401. Để trống biến đó (như `.env.example`) để chạy offline.

## Mở rộng

- Thêm case vào `golden_dataset.yaml` theo category (safety, citation, injection...).
- Thay auto-check trong `run_eval._check` nếu cần rule riêng.
- Khi setup vector store thật, cập nhật `retrieve_node` — eval sẽ tự đối chiếu citation.

## Tại sao quan trọng

- Cohort 1: chỉ 2/12 teams có evaluation evidence → mất điểm BTC.
- Eval framework = bằng chứng testing cho Demo Day + regression safety khi đổi prompt/model.
