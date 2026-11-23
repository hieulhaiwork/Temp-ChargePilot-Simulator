# ---- Stage 1: Build ----
FROM python:3.12-slim AS builder

# Cài dependency vào venv riêng (không dùng /root/.local: user non-root
# ở stage production không đọc được /root).
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH

# Chỉ dependency LÚC CHẠY — công cụ dev/test (ruff, pytest…) nằm ở requirements.txt và không vào image
# (gói free ít RAM, build chậm — docs/plan/50-devops.md §5).
COPY requirements-runtime.txt .
RUN pip install --no-cache-dir -r requirements-runtime.txt
# Engine HybridSimulator cần ev2gym, nhưng metadata ev2gym kéo gurobipy/pandas/matplotlib… không dùng tới → --no-deps;
# phụ thuộc thật (gymnasium, numpy, scipy) đã cài ở bước trên. Cùng phiên bản với ci.yml và Makefile (`make install`).
#   Dòng import kiểm ngay lúc build: thiếu phụ thuộc thì build đỏ thay vì container chết lúc chạy.
RUN pip install --no-cache-dir --no-deps ev2gym==2.0.0 \
    && python -c "import ev2gym.models.ev, ev2gym.models.ev_charger"

# ---- Stage 2: Production ----
FROM python:3.12-slim

ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv

# Security: run as non-root user
RUN useradd -m appuser

# Copy application code (phạm vi do .dockerignore quyết định)
COPY . .

# Create data directory with correct ownership
RUN mkdir -p /app/data && chown -R appuser:appuser /app

USER appuser

# Hosting (Render, ...) cấp port qua biến PORT; local mặc định 8000.
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import os, urllib.request as u; u.urlopen('http://localhost:%s/health' % os.environ.get('PORT', '8000'))" || exit 1

# 1) `alembic upgrade head` TRƯỚC khi nhận request: Render free không có shell hay lệnh pre-deploy. Migration lỗi
#    → container không lên → health check fail → Render giữ bản cũ (ADR-005).
# 2) ĐÚNG MỘT worker: runtime của trạm, event bus, sổ kết nối WebSocket và checkpoint chat nằm trong RAM của
#    process (ADR-007). Tăng worker là hỏng realtime.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
