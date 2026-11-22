"""Fitness test kiến trúc — khoá các ranh giới an toàn của ChargePilot bằng code.

Vì sao tồn tại: PRD yêu cầu "LLM không bao giờ gửi lệnh thẳng tới simulator" và "bảo vệ
khẩn cấp độc lập với AI". Quy ước bằng lời sẽ bị phá lúc gấp deadline; các test này fail
ngay khi ai đó import sai tầng. Muốn nới một quy tắc → sửa ở đây + ghi ADR (docs/adr/).

Các ranh giới:
  1. Import giữa các package trong src/ (BOUNDARIES) — ADR-002, ADR-005, ADR-007.
  2. Chỉ guard/dispatcher.py đụng phần GHI của simulator — ADR-002.
  3. Chỉ src/db/** và services/repository.py biết ORM — ADR-005.
  4. Hợp đồng dữ liệu (src/models) không phụ thuộc thư viện hạ tầng.
  5. Agent không có đường nào tạo lệnh điều khiển trạm — FR5.
  6. frontend/ không import gì từ ngoài frontend/ — ADR-009.
"""

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
FRONTEND_SRC = ROOT / "frontend" / "src"

# package trong src/ → các prefix module KHÔNG được import
BOUNDARIES: dict[str, tuple[str, ...]] = {
    # FR5: Agent chỉ đi qua src/services — không chạm bộ tối ưu, Guard, simulator, DB
    "agents": ("src.simulator", "src.guard", "src.optimizer", "src.forecast", "src.db", "src.api"),
    # ADR-007: router chỉ gọi src/services (và src.agents.graph cho /chat) — không gọi thẳng các trụ hay DB
    "api": ("src.guard", "src.optimizer", "src.simulator", "src.forecast", "src.db"),
    # F4: Guard là code xác định, chạy được khi LLM sập
    "guard": ("src.agents", "src.services.llm", "src.api", "src.db", "src.optimizer", "src.forecast"),
    # Optimizer thuần: context vào → plan ra (benchmark A–D cùng interface)
    "optimizer": ("src.agents", "src.api", "src.services", "src.simulator", "src.guard", "src.db", "src.forecast"),
    "forecast": ("src.agents", "src.api", "src.services", "src.simulator", "src.guard", "src.optimizer", "src.db"),
    "simulator": ("src.agents", "src.api", "src.services", "src.optimizer", "src.guard", "src.db", "src.forecast"),
    # ADR-005: tầng persistence chỉ biết hợp đồng dữ liệu và cấu hình
    "db": (
        "src.agents",
        "src.api",
        "src.services",
        "src.optimizer",
        "src.guard",
        "src.simulator",
        "src.forecast",
    ),
    # Hợp đồng dữ liệu không phụ thuộc tầng nào
    "models": (
        "src.agents",
        "src.api",
        "src.services",
        "src.optimizer",
        "src.guard",
        "src.simulator",
        "src.forecast",
        "src.db",
        "src.config",
    ),
}

# Chỉ các file này được đụng tới phần GHI của simulator
ACTUATOR_ALLOWED = {SRC / "guard" / "dispatcher.py"}

# ADR-005: chỉ những nơi này được import ORM
ORM_MODULES = ("sqlalchemy", "alembic", "src.db")
ORM_ALLOWED_DIR = SRC / "db"
ORM_ALLOWED_FILES = {SRC / "services" / "repository.py"}

# Hợp đồng dữ liệu chỉ dùng thư viện chuẩn + pydantic
MODELS_FORBIDDEN_THIRD_PARTY = ("sqlalchemy", "fastapi", "starlette", "langchain", "langgraph", "openai", "yaml")


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
            found.update(f"{node.module}.{alias.name}" for alias in node.names)
    return found


def _violates(module: str, forbidden: tuple[str, ...]) -> bool:
    return any(module == prefix or module.startswith(prefix + ".") for prefix in forbidden)


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


# ---- 1. Ranh giới import giữa các package -------------------------------------------------


@pytest.mark.parametrize("package", sorted(BOUNDARIES))
def test_package_respects_import_boundaries(package):
    offenders = [
        f"{_rel(path)} imports {module}"
        for path in sorted((SRC / package).rglob("*.py"))
        for module in sorted(_imported_modules(path))
        if _violates(module, BOUNDARIES[package])
    ]
    assert not offenders, "Vi phạm ranh giới kiến trúc:\n" + "\n".join(offenders)


def test_every_src_package_has_a_boundary_rule_or_is_a_known_integrator():
    """Thêm package mới vào src/ thì phải quyết định ranh giới của nó ngay (không để lọt lưới)."""
    packages = {path.name for path in SRC.iterdir() if path.is_dir() and (path / "__init__.py").exists()}
    integrators = {"services"}  # tầng ứng dụng: được phép nối các trụ với nhau
    assert packages == set(BOUNDARIES) | integrators, (
        f"Chưa khai báo ranh giới cho: {packages - set(BOUNDARIES) - integrators}"
    )


# ---- 2. Chokepoint tới trạm (ADR-002) ------------------------------------------------------


def test_only_dispatcher_touches_station_actuator():
    """FR12/AC6: chỉ guard/dispatcher.py được import StationActuator hoặc gọi apply_commands."""
    offenders = []
    for path in sorted(SRC.rglob("*.py")):
        if path in ACTUATOR_ALLOWED or path.is_relative_to(SRC / "simulator"):
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and any(a.name == "StationActuator" for a in node.names):
                offenders.append(f"{_rel(path)}:{node.lineno} import StationActuator")
            if isinstance(node, ast.Attribute) and node.attr == "apply_commands":
                offenders.append(f"{_rel(path)}:{node.lineno} gọi .apply_commands")
    assert not offenders, "Lệnh tới trạm phải đi qua guard/dispatcher.py:\n" + "\n".join(offenders)


# ---- 3. ORM chỉ nằm sau repository (ADR-005) -----------------------------------------------


def test_only_repository_and_db_package_touch_orm():
    offenders = []
    for path in sorted(SRC.rglob("*.py")):
        if path.is_relative_to(ORM_ALLOWED_DIR) or path in ORM_ALLOWED_FILES:
            continue
        offenders += [f"{_rel(path)} imports {m}" for m in sorted(_imported_modules(path)) if _violates(m, ORM_MODULES)]
    assert not offenders, "Chỉ src/db/** và src/services/repository.py được dùng ORM (ADR-005):\n" + "\n".join(
        offenders
    )


def test_repository_never_leaks_orm_rows_through_its_signatures():
    """Vào và ra của repository là model Pydantic của src/models — không phải lớp ORM."""
    tree = ast.parse((SRC / "services" / "repository.py").read_text(encoding="utf-8"))
    leaked = [
        f"{node.name}: {ast.unparse(annotation)}"
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        for annotation in [node.returns, *(arg.annotation for arg in node.args.args + node.args.kwonlyargs)]
        if annotation is not None and "Row" in ast.unparse(annotation)
    ]
    assert not leaked, f"Chữ ký repository lộ lớp ORM: {leaked}"


# ---- 4. Hợp đồng dữ liệu đứng độc lập ------------------------------------------------------


def test_models_do_not_depend_on_infrastructure_libraries():
    offenders = [
        f"{_rel(path)} imports {module}"
        for path in sorted((SRC / "models").rglob("*.py"))
        for module in sorted(_imported_modules(path))
        if _violates(module, MODELS_FORBIDDEN_THIRD_PARTY)
    ]
    assert not offenders, "src/models chỉ dùng thư viện chuẩn + pydantic:\n" + "\n".join(offenders)


# ---- 5. Agent không ra lệnh trạm (FR5) -----------------------------------------------------


def test_agent_package_cannot_construct_station_commands():
    """Agent không import Command / CommandType → về cấu trúc không tạo được lệnh điều khiển trạm."""
    offenders = [
        f"{_rel(path)} imports {module}"
        for path in sorted((SRC / "agents").rglob("*.py"))
        for module in sorted(_imported_modules(path))
        if module
        in {"src.models.control.Command", "src.models.control.CommandType", "src.models.control.CommandSource"}
    ]
    assert not offenders, "Agent chỉ đề xuất qua services — không tự tạo Command (FR5):\n" + "\n".join(offenders)


def test_agent_tools_only_call_the_services_layer():
    """Tool chỉ import src.services.* và src.models.* (cùng thư viện ngoài) — không còn đường tắt nào khác."""
    allowed = ("src.services", "src.models", "src.agents", "src.config")
    offenders = [
        f"{_rel(path)} imports {module}"
        for path in sorted((SRC / "agents" / "tools").rglob("*.py"))
        for module in sorted(_imported_modules(path))
        if module.startswith("src.") and not _violates(module, allowed)
    ]
    assert not offenders, "\n".join(offenders)


# ---- 6. frontend chỉ nhận openapi.json từ backend (ADR-009) --------------------------------

_TS_IMPORT = re.compile(r"""(?:from\s+|import\s*\(\s*|require\s*\(\s*)["']([^"']+)["']""")


def _escapes_frontend(source_file: Path, specifier: str) -> bool:
    if not specifier.startswith("."):
        return False  # gói npm hoặc alias "@/…" (trỏ vào frontend/src)
    target = (source_file.parent / specifier).resolve()
    return not target.is_relative_to(FRONTEND_SRC.parent)


@pytest.mark.skipif(not FRONTEND_SRC.is_dir(), reason="chưa có frontend/")
def test_frontend_only_consumes_generated_types():
    offenders = [
        f"{_rel(path)} imports {specifier}"
        for path in sorted(FRONTEND_SRC.rglob("*.ts*"))
        for specifier in _TS_IMPORT.findall(path.read_text(encoding="utf-8"))
        if _escapes_frontend(path, specifier)
    ]
    assert not offenders, "frontend/ không được import ra ngoài frontend/ (ADR-009):\n" + "\n".join(offenders)


@pytest.mark.skipif(not FRONTEND_SRC.is_dir(), reason="chưa có frontend/")
def test_frontend_never_puts_token_in_a_url():
    """ADR-006: token đi trong header / bản tin đầu của WebSocket — không nằm trong query string."""
    pattern = re.compile(r"[?&]token=")
    offenders = [
        _rel(path)
        for path in sorted(FRONTEND_SRC.rglob("*.ts*"))
        if path.name != "schema.d.ts" and "test" not in path.parts and pattern.search(path.read_text(encoding="utf-8"))
    ]
    assert not offenders, f"Token không được đặt trên URL: {offenders}"


# ---- Tự kiểm: bộ dò phải bắt được vi phạm --------------------------------------------------


def test_boundary_checker_detects_violation(tmp_path):
    """Tự kiểm test: một import cấm phải bị phát hiện (tránh test xanh vì parse sai)."""
    bad = tmp_path / "bad.py"
    bad.write_text("from src.simulator.base import StationActuator\n", encoding="utf-8")
    modules = _imported_modules(bad)
    assert _violates("src.simulator.base.StationActuator", BOUNDARIES["agents"])
    assert "src.simulator.base" in modules


def test_orm_checker_detects_violation(tmp_path):
    bad = tmp_path / "bad.py"
    bad.write_text("from sqlalchemy.orm import Session\nfrom src.db import tables\n", encoding="utf-8")
    assert all(_violates(module, ORM_MODULES) for module in _imported_modules(bad))


def test_frontend_checker_detects_escape():
    inside = FRONTEND_SRC / "lib" / "api" / "client.ts"
    assert _escapes_frontend(inside, "../../../../src/models/api")
    assert not _escapes_frontend(inside, "./schema")
    assert not _escapes_frontend(inside, "@/lib/env")
    assert _TS_IMPORT.findall('import x from "../../../../src/a";\nconst y = await import("./b");') == [
        "../../../../src/a",
        "./b",
    ]
