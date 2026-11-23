.PHONY: install run test lint format format-check docs-check openapi openapi-check migrate eval eval-strict eval-agent \
	benchmark check check-all web-check typecheck clean

# Windows không có `python3`; trong venv / CI lệnh `python` luôn có. Ghi đè: make test PYTHON=python3
PYTHON ?= python
export PYTHONIOENCODING := utf-8

# Cài môi trường dev/CI. ev2gym phải --no-deps (lý do: requirements-runtime.txt, khối "Duyệt 2026-11-23") nên
# không nằm trong requirements file. Cùng phiên bản với Dockerfile và .github/workflows/ci.yml.
EV2GYM_VERSION := 2.0.0

install:
	$(PYTHON) -m pip install -r requirements.txt
	$(PYTHON) -m pip install --no-deps ev2gym==$(EV2GYM_VERSION)

run:
	uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

test:
	pytest tests/ -v

lint:
	ruff check src/ tests/

format:
	ruff format src/ tests/

format-check:
	ruff format --check src/ tests/

docs-check:
	$(PYTHON) scripts/check_docs.py

# Hợp đồng API cho web (ADR-009): ghi lại frontend/openapi.json sau khi đổi model/endpoint,
# rồi chạy `npm run gen:api` trong frontend/.
openapi:
	$(PYTHON) scripts/export_openapi.py

openapi-check:
	$(PYTHON) scripts/export_openapi.py --check

# Áp migration schema (ADR-005). DB lấy từ DATABASE_URL / .env.
migrate:
	alembic upgrade head

# Eval regression của template — chạy agent qua golden dataset, judge tách generator.
# Mặc định ghi eval/results/report.md (file được track). Chạy thử: thêm `--out <đường dẫn tạm>`.
# Không cần API key (offline stub mode); có key là chạy LLM thật.
eval:
	$(PYTHON) eval/run_eval.py

eval-strict:
	$(PYTHON) eval/run_eval.py --strict

# Eval Agent F1 trên bộ câu yêu cầu sạc có nhãn (PRD §8). --offline: chỉ kiểm dataset + ngưỡng, không gọi LLM.
eval-agent:
	$(PYTHON) eval/run_agent_eval.py --offline

# Benchmark A–D của ChargePilot (AC7) — cùng kịch bản config/scenarios/, cùng biểu giá.
# Xuất eval/results/benchmark.md + benchmark.json. Exit 2 khi pipeline còn stub.
benchmark:
	$(PYTHON) eval/run_benchmark.py

typecheck:
	mypy src/

# Bộ check bắt buộc sau mỗi thay đổi code (không sửa file): lint + format + test + docs.
check: lint format-check test docs-check

# Như `check`, thêm các bước CI sẽ chạy: hợp đồng OpenAPI và eval offline.
check-all: check openapi-check eval-agent

# Bốn bước CI của web.
web-check:
	cd frontend && npm run lint && npm run typecheck && npm test && npm run build

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -type d -name .ruff_cache -exec rm -rf {} +
