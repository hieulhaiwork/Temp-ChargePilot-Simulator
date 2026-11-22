"""FastAPI app của ChargePilot — gắn router, quy ước lỗi (ADR-008), /health và /ready.

Stub chưa làm `raise NotImplementedError("[Txx] …")` → 501 kèm task_id (ADR-004).
Service ném DomainError → HTTP theo mã lỗi. Lỗi không lường trước → 500 với thông điệp chung;
chi tiết chỉ nằm trong log kèm request_id.
"""

import asyncio
import logging
import re
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.api import auth, catalog, operations, resident, simulation, ws
from src.api.routes import router
from src.config import get_settings
from src.models.api import ErrorCode, ErrorResponse, ReadinessReport
from src.services import auth as auth_service
from src.services import catalog as catalog_service
from src.services import control_loop, repository, runtime
from src.services.errors import DomainError

API_PREFIX = "/api/v1"
REQUEST_ID_HEADER = "X-Request-ID"

logger = logging.getLogger("chargepilot.app")

_TASK_ID = re.compile(r"\[(T\d+\.\d+[a-z]?)")  # "[T2.2] …" hoặc "[T1.5/T3.4] …" → lấy task đầu tiên
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_HTTP_CODES = {401: ErrorCode.UNAUTHENTICATED, 403: ErrorCode.FORBIDDEN, 404: ErrorCode.NOT_FOUND}


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info("Starting %s in %s mode", settings.app_name, settings.app_env)
    # T1.7: seed tài khoản demo từ SEED_USERS_JSON (Render free không có shell). Lỗi DB không chặn app lên —
    # /ready sẽ báo database lỗi.
    try:
        auth_service.ensure_seed_users()
    except Exception:
        logger.exception("Seed tài khoản demo thất bại")
    # T2.6: vòng nền (bước simulator, TICK, hết hạn phê duyệt) — chỉ khi CONTROL_LOOP_ENABLED. Tắt thì sự kiện vẫn
    # được xử lý ngay trong request (ADR-007), nhưng xe đến / rời theo giờ chỉ được thấy ở request kế tiếp.
    stop = asyncio.Event()
    background: asyncio.Task | None = None
    if settings.control_loop_enabled:
        background = asyncio.create_task(control_loop.run_forever(stop, runtime.get_runtime()))
    yield
    stop.set()
    if background is not None:
        await background
    repository.dispose()
    logger.info("Shutting down")


_ERROR = {"model": ErrorResponse}
app = FastAPI(
    title="ChargePilot API",
    description=(
        "AI Agent quản lý & tối ưu trạm sạc EV (SC-16, T019). "
        "Endpoint trả 501 là phần skeleton chưa implement — `task_id` ghi mã task (vd T2.2)."
    ),
    version="1.0.0",
    lifespan=lifespan,
    # Hiện envelope lỗi trên OpenAPI để frontend có type (ADR-008).
    responses={401: _ERROR, 403: _ERROR, 404: _ERROR, 409: _ERROR, 501: _ERROR, 503: _ERROR},
)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_origin_regex=settings.cors_origin_regex or None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[REQUEST_ID_HEADER],
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next) -> Response:
    """Mỗi request một id: nhận từ client nếu hợp lệ, không thì sinh mới; trả lại trong header."""
    incoming = request.headers.get(REQUEST_ID_HEADER, "")
    request.state.request_id = incoming if _SAFE_REQUEST_ID.match(incoming) else uuid4().hex
    response = await call_next(request)
    response.headers[REQUEST_ID_HEADER] = request.state.request_id
    return response


def _error(
    request: Request,
    status_code: int,
    code: ErrorCode,
    detail: str,
    *,
    task_id: str | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body = ErrorResponse(
        detail=detail,
        code=code,
        task_id=task_id,
        request_id=getattr(request.state, "request_id", None),
        status="not_implemented" if code == ErrorCode.NOT_IMPLEMENTED else None,
    )
    return JSONResponse(
        status_code=status_code, content=body.model_dump(mode="json", exclude_none=True), headers=headers
    )


@app.exception_handler(NotImplementedError)
async def not_implemented_handler(request: Request, exc: NotImplementedError) -> JSONResponse:
    """Contract-first: endpoint đã có hợp đồng (OpenAPI) nhưng logic chưa làm → 501, không phải 500."""
    detail = str(exc) or "Chưa implement"
    match = _TASK_ID.search(detail)
    return _error(request, 501, ErrorCode.NOT_IMPLEMENTED, detail, task_id=match.group(1) if match else None)


@app.exception_handler(DomainError)
async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    return _error(request, exc.http_status, exc.code, exc.detail)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """401/403/404 do router và deps ném — bọc vào cùng envelope, giữ header (vd WWW-Authenticate)."""
    code = _HTTP_CODES.get(exc.status_code, ErrorCode.HTTP_ERROR)
    return _error(request, exc.status_code, code, str(exc.detail), headers=getattr(exc, "headers", None))


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Lỗi không lường trước: log đầy đủ kèm request_id, trả thông điệp chung (không lộ nội bộ)."""
    request_id = getattr(request.state, "request_id", None)
    logger.exception("FAILED %s %s request_id=%s", request.method, request.url.path, request_id)
    return _error(
        request, 500, ErrorCode.INTERNAL_ERROR, "Lỗi máy chủ. Vui lòng thử lại; nếu còn lỗi, báo kèm request_id."
    )


app.include_router(router, prefix=API_PREFIX)  # F1 chat: /chat, /chat/resume, /status
for feature_router in (auth.router, catalog.router, resident.router, operations.router, simulation.router, ws.router):
    app.include_router(feature_router, prefix=API_PREFIX)


@app.get("/health", tags=["system"])
async def health():
    """Liveness — KHÔNG đụng DB. Render healthCheckPath và ping giữ thức của frontend gọi vào đây."""
    return {"status": "ok", "env": settings.app_env}


def _check(probe) -> str:
    try:
        probe()
    except NotImplementedError as exc:
        match = _TASK_ID.search(str(exc))
        return f"not_implemented [{match.group(1)}]" if match else "not_implemented"
    except Exception:
        logger.exception("FAILED readiness probe %s", getattr(probe, "__name__", probe))
        return "error"
    return "ok"


def _load_config() -> None:
    catalog_service.load_station_config()
    catalog_service.load_tariff()
    catalog_service.load_vehicle_catalog()


@app.get("/ready", response_model=ReadinessReport, tags=["system"], responses={503: {"model": ReadinessReport}})
async def ready(response: Response) -> ReadinessReport:
    """Readiness — config nạp được và DB trả lời. Phần còn stub báo `not_implemented [Txx]`, không tính là lỗi."""
    checks = {
        "config": _check(_load_config),
        "database": await run_in_threadpool(_check, repository.ping),
    }
    degraded = "error" in checks.values()
    if degraded:
        response.status_code = 503
    return ReadinessReport(status="degraded" if degraded else "ok", checks=checks)
