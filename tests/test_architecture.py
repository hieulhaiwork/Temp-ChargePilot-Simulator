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
  7. Hợp đồng core dùng chung (scenario, observation, budget, limits, physics) nằm ở src/models, thuần stdlib;
     simulator chạy standalone không cần stack backend; chỉ adapter chuyển tiếp chạm src.simulator.src — ADR-019.
"""

import ast
import os
import re
import subprocess
import sys
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
    # ADR-019: Guard không import simulator (simulator dùng guard.physical.validator → cấm chiều ngược để không vòng)
    "guard": ("src.agents", "src.services.llm", "src.api", "src.db", "src.optimizer", "src.forecast", "src.simulator"),
    # Optimizer thuần: context vào → plan ra (benchmark A–D cùng interface)
    "optimizer": ("src.agents", "src.api", "src.services", "src.simulator", "src.guard", "src.db", "src.forecast"),
    "forecast": ("src.agents", "src.api", "src.services", "src.simulator", "src.guard", "src.optimizer", "src.db"),
    # ADR-019: simulator dùng thuật toán của optimizer (dispatch/zones/coordination/registry) — không dùng LP backend cũ;
    # phạm vi được phép khoá chặt hơn ở test_simulator_uses_only_algorithm_packages
    # và chỉ Physical Guard gốc (guard.physical.validator) — khoá ở test_simulator_uses_only_the_physical_validator
    "simulator": ("src.agents", "src.api", "src.services", "src.db", "src.forecast"),
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


def _module_name(path: Path, root: Path = ROOT) -> str:
    parts = list(path.relative_to(root).with_suffix("").parts)
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def _resolve_from(node: ast.ImportFrom, path: Path, root: Path) -> str | None:
    """Tên tuyệt đối của `from <module> import …`, kể cả import tương đối (`from ..x import y`)."""
    if not node.level:
        return node.module
    package = _module_name(path, root).split(".")
    if path.name != "__init__.py":
        package = package[:-1]
    if node.level - 1 > len(package):
        return None
    base = package[: len(package) - (node.level - 1)]
    return ".".join([*base, node.module] if node.module else base) or None


def _imported_modules(path: Path, root: Path = ROOT) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = _resolve_from(node, path, root)
            if module:
                found.add(module)
                found.update(f"{module}.{alias.name}" for alias in node.names)
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


# ---- 7. Hợp đồng core dùng chung + simulator standalone (ADR-019) ---------------------------

# Hợp đồng mà optimizer, physical guard và simulator cùng dùng. Chỉ stdlib + chính nhóm này: simulator standalone
# (requirements riêng, không có pydantic) phải import được.
CORE_CONTRACTS = (
    "src.models.simulation_core",
    "src.models.charging_physics",
    "src.models.physical_constraints",
    "src.models.physical_limits",
    "src.models.scheduling",
    "src.models.decisions",  # ADR-019 Phase 3: ProposedDecision / ApprovedDecision / AppliedResult / TimeConfig
)
# Vị trí cũ trong simulator — nay chỉ re-export. Ngoài src/simulator/ phải import thẳng từ src.models.
CORE_CONTRACT_SHIMS = {
    "src.simulator.src.scenario": "src.models.simulation_core",
    "src.simulator.src.charging_models.base": "src.models.charging_physics",
    "src.simulator.src.safety.constraints": "src.models.physical_constraints",
    "src.simulator.src.safety.limits": "src.models.physical_limits",
    "src.simulator.src.observations": "src.models.scheduling.observations",
    "src.simulator.src.dispatch.base": "src.models.scheduling.dispatch",
    "src.simulator.src.coordination.base": "src.models.scheduling.coordination",
    "src.simulator.src.optimizers.base": "src.models.scheduling.optimization",
}
# Adapter chuyển tiếp còn chạm engine / thuật toán / guard của simulator. Phase 2–3 (ADR-019) thu hẹp danh sách này.
SIMULATOR_CORE_TRANSITIONAL = {
    "src/simulator/hybrid_station.py",
    "src/services/hybrid_planner.py",
    "tests/test_simulator/test_hybrid_station.py",
    # Phase 3: differential CLI ↔ backend phải dựng HybridSimulator + algorithms của simulator cạnh HybridStation.
    "tests/test_refactor/test_differential.py",
}
# Stack backend: simulator standalone không được kéo theo
BACKEND_STACK = ("pydantic", "fastapi", "starlette", "sqlalchemy", "alembic", "langchain", "langgraph", "openai")


def _module_files(prefix: str) -> list[Path]:
    base = ROOT.joinpath(*prefix.split("."))
    if base.is_dir():
        return sorted(base.rglob("*.py"))
    return [path for path in [base.with_suffix(".py")] if path.exists()]


def _is_core_contract(module: str) -> bool:
    return _violates(module, CORE_CONTRACTS)


def test_core_contracts_are_pure_stdlib():
    offenders = []
    for prefix in CORE_CONTRACTS:
        for path in _module_files(prefix):
            for module in sorted(_imported_modules(path)):
                top = module.split(".")[0]
                if top == "src":
                    if not _is_core_contract(module):
                        offenders.append(f"{_rel(path)} imports {module}")
                elif top not in sys.stdlib_module_names and top != "__future__":
                    offenders.append(f"{_rel(path)} imports {module}")
    assert not offenders, "Hợp đồng core chỉ dùng stdlib + chính nhóm hợp đồng (ADR-019):\n" + "\n".join(offenders)


def test_core_contract_shims_reexport_the_same_objects():
    """Vị trí cũ trong simulator trả về ĐÚNG đối tượng ở src.models (isinstance / identity không đổi)."""
    import importlib

    for old, new in CORE_CONTRACT_SHIMS.items():
        shim, target = importlib.import_module(old), importlib.import_module(new)
        assert shim.__all__, old
        for name in shim.__all__:
            assert getattr(shim, name) is getattr(target, name), f"{old}.{name}"


def _python_files_outside_simulator() -> list[Path]:
    roots = [SRC, ROOT / "tests", ROOT / "eval", ROOT / "scripts"]
    return [
        path
        for root in roots
        for path in sorted(root.rglob("*.py"))
        if not path.is_relative_to(SRC / "simulator") and "__pycache__" not in path.parts
    ]


def test_contracts_are_imported_from_models_outside_the_simulator():
    offenders = [
        f"{_rel(path)} imports {module} — dùng {CORE_CONTRACT_SHIMS[module]}"
        for path in _python_files_outside_simulator()
        for module in sorted(_imported_modules(path))
        if module in CORE_CONTRACT_SHIMS
    ]
    assert not offenders, "\n".join(offenders)


# CLI của simulator (cùng package) được dùng engine nội bộ
SIMULATOR_CLI = {"src/simulator/run.py", "src/simulator/benchmark.py", "src/simulator/benchmark_mvp3.py"}


def test_only_transitional_adapters_reach_into_simulator_internals():
    candidates = _python_files_outside_simulator() + sorted((SRC / "simulator").glob("*.py"))
    offenders = [
        f"{_rel(path)} imports {module}"
        for path in candidates
        if _rel(path) not in SIMULATOR_CORE_TRANSITIONAL | SIMULATOR_CLI
        for module in sorted(_imported_modules(path))
        if module.startswith("src.simulator.src.")
    ]
    assert not offenders, "Chỉ adapter chuyển tiếp (ADR-019) được chạm src.simulator.src:\n" + "\n".join(offenders)


CORE_LAYERS = ("models", "optimizer", "guard", "simulator")


def _layer_graph(root: Path, layers: tuple[str, ...]) -> dict[str, set[str]]:
    """Cạnh tầng → tầng trong `<root>/src`, tính cả import tuyệt đối lẫn tương đối."""
    graph: dict[str, set[str]] = {layer: set() for layer in layers}
    for layer in layers:
        for path in (root / "src" / layer).rglob("*.py"):
            for module in _imported_modules(path, root):
                parts = module.split(".")
                if len(parts) > 1 and parts[0] == "src" and parts[1] in layers and parts[1] != layer:
                    graph[layer].add(parts[1])
    return graph


def _layers_in_cycles(graph: dict[str, set[str]]) -> list[str]:
    def reaches(start: str, goal: str, seen: frozenset[str]) -> bool:
        return any(nxt == goal or (nxt not in seen and reaches(nxt, goal, seen | {nxt})) for nxt in graph[start])

    return [layer for layer in graph if reaches(layer, layer, frozenset({layer}))]


# Gói thuật toán của optimizer dùng chung cho simulator standalone + backend (ADR-019). LP backend cũ (base, baselines,
# mpc, lp_model, horizon, assignment, strategies) đã xoá ở Phase 3 — src/optimizer chỉ còn các gói này.
OPTIMIZER_ALGORITHMS = (
    "src.optimizer.dispatch",
    "src.optimizer.zones",
    "src.optimizer.coordination",
    "src.optimizer.registry",
)


def test_simulator_uses_only_algorithm_packages_of_the_optimizer():
    offenders = [
        f"{_rel(path)} imports {module}"
        for path in sorted((SRC / "simulator").rglob("*.py"))
        for module in sorted(_imported_modules(path))
        if _violates(module, ("src.optimizer",)) and not _violates(module, OPTIMIZER_ALGORITHMS)
    ]
    assert not offenders, "Simulator chỉ dùng gói thuật toán của optimizer (ADR-019):\n" + "\n".join(offenders)


def test_simulator_uses_only_the_physical_validator_of_the_guard():
    """Simulator gọi Physical Guard gốc; không chạm luật nghiệp vụ / consent / HITL / dispatcher / adapter backend."""
    offenders = [
        f"{_rel(path)} imports {module}"
        for path in sorted((SRC / "simulator").rglob("*.py"))
        for module in sorted(_imported_modules(path))
        if _violates(module, ("src.guard",)) and not _violates(module, ("src.guard.physical.validator",))
    ]
    assert not offenders, "\n".join(offenders)


def test_physical_guard_package_keeps_the_old_public_api_without_loading_the_backend():
    code = (
        "import sys; import src.guard.physical as p; assert 'pydantic' not in sys.modules, 'eager adapter';"
        "from src.guard.physical import check_dispatch, check_site_allocation, check_connector_allocation;"
        "from src.guard.physical import adapter; assert check_dispatch is adapter.check_dispatch;"
        "from src.guard.physical import validator; assert p.guard is validator.guard"
    )
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr


def test_optimizer_algorithm_packages_depend_only_on_contracts():
    """dispatch / zones / coordination / registry chỉ import hợp đồng core + chính nhóm thuật toán + numpy/scipy."""
    offenders = []
    for prefix in OPTIMIZER_ALGORITHMS:
        for path in _module_files(prefix):
            for module in sorted(_imported_modules(path)):
                if module.startswith("src.") and not (
                    _is_core_contract(module) or _violates(module, OPTIMIZER_ALGORITHMS)
                ):
                    offenders.append(f"{_rel(path)} imports {module}")
    assert not offenders, "\n".join(offenders)


def test_policy_bundles_have_a_single_source():
    """B0 / M2b / M3a / M3b chỉ khai báo ở src/optimizer/registry.py; benchmark và backend dùng lại, không chép."""
    from src.optimizer.registry import POLICIES
    from src.services import hybrid_planner
    from src.simulator import benchmark_mvp3

    assert benchmark_mvp3.POLICIES is POLICIES
    assert {strategy.value: bundle for strategy, bundle in hybrid_planner.POLICIES.items()} == POLICIES
    assert all(bundle is POLICIES[strategy.value] for strategy, bundle in hybrid_planner.POLICIES.items())


def test_core_layers_have_no_import_cycle():
    """Đồ thị gói models / optimizer / guard / simulator phải một chiều (không vòng)."""
    graph = _layer_graph(ROOT, CORE_LAYERS)
    cycles = _layers_in_cycles(graph)
    assert not cycles, f"Vòng phụ thuộc giữa các tầng core: {cycles} — {graph}"


_STANDALONE_PROBE = """
import importlib.abc, sys
BLOCKED = {blocked!r}
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in BLOCKED:
            raise ImportError("standalone simulator must not import " + name)
sys.meta_path.insert(0, Block())
for module in {modules!r}:
    importlib.import_module(module)
"""


def test_simulator_imports_without_the_backend_stack():
    """Chế độ standalone: CLI, benchmark, golden, DecisionTrace không cần FastAPI / DB / LLM / pydantic."""
    modules = (
        "src.simulator.run",
        "src.simulator.benchmark",
        "src.simulator.benchmark_mvp3",
        "src.simulator.src.algorithms",
        "src.simulator.src.engine.hybrid",
        "src.simulator.src.evaluation.extended",
        "src.simulator.src.evaluation.trace",
        *CORE_CONTRACTS,
        *(prefix for prefix in OPTIMIZER_ALGORITHMS if prefix != "src.optimizer.registry"),
        "src.optimizer.zones.ac_lp",
        "src.optimizer.zones.rolling_lp",
        "src.optimizer.coordination.dynamic_slack",
        "src.optimizer.dispatch.least_laxity",
        "src.optimizer.registry",
        "src.guard.physical",
        "src.guard.physical.validator",
    )
    code = _STANDALONE_PROBE.format(blocked=set(BACKEND_STACK), modules=modules)
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr


def test_simulator_script_mode_entrypoint_runs():
    """`python src/simulator/run.py` (chế độ script trong README simulator) vẫn chạy."""
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    result = subprocess.run(
        [sys.executable, str(SRC / "simulator" / "run.py"), "--list-scenarios"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "mvp1" in result.stdout.split()


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


def test_relative_imports_are_resolved_to_absolute_modules(tmp_path):
    pkg = tmp_path / "src" / "simulator" / "src" / "engine"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("from . import hybrid\nfrom .queue import Q\n", encoding="utf-8")
    mod = pkg / "hybrid.py"
    mod.write_text("from ..algorithms import resolve\nfrom . import queue\nfrom .... import models\n", encoding="utf-8")
    found = _imported_modules(mod, tmp_path)
    assert {"src.simulator.src.algorithms", "src.simulator.src.algorithms.resolve"} <= found
    assert {"src.simulator.src.engine", "src.simulator.src.engine.queue"} <= found
    assert "src.models" in found  # 4 chấm từ src/simulator/src/engine → src
    init = _imported_modules(pkg / "__init__.py", tmp_path)
    assert {"src.simulator.src.engine.hybrid", "src.simulator.src.engine.queue.Q"} <= init
    # Kiểm trên code thật: engine của simulator chỉ dùng import tương đối.
    real = _imported_modules(SRC / "simulator" / "src" / "engine" / "hybrid.py")
    assert "src.simulator.src.engine.queue" in real


def test_cycle_detector_finds_a_cycle_made_only_of_relative_imports(tmp_path):
    """Negative test: vòng optimizer ↔ guard chỉ bằng import tương đối phải bị phát hiện."""
    for layer, imports in (("optimizer", "from ..guard import rules\n"), ("guard", "from ..optimizer import lp\n")):
        (tmp_path / "src" / layer).mkdir(parents=True)
        (tmp_path / "src" / layer / "__init__.py").write_text("", encoding="utf-8")
        (tmp_path / "src" / layer / "mod.py").write_text(imports, encoding="utf-8")
    graph = _layer_graph(tmp_path, ("optimizer", "guard"))
    assert graph == {"optimizer": {"guard"}, "guard": {"optimizer"}}
    assert sorted(_layers_in_cycles(graph)) == ["guard", "optimizer"]
    (tmp_path / "src" / "guard" / "mod.py").write_text("from .rules import x\n", encoding="utf-8")
    assert not _layers_in_cycles(_layer_graph(tmp_path, ("optimizer", "guard")))


def test_boundary_checker_sees_relative_imports(tmp_path):
    bad = tmp_path / "src" / "optimizer" / "zones" / "lp.py"
    bad.parent.mkdir(parents=True)
    bad.write_text("from ...guard.physical import validator\n", encoding="utf-8")
    assert any(_violates(m, BOUNDARIES["optimizer"]) for m in _imported_modules(bad, tmp_path))


def test_standalone_probe_really_blocks_the_backend_stack():
    code = _STANDALONE_PROBE.format(blocked=set(BACKEND_STACK), modules=("pydantic",))
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=False)
    assert result.returncode != 0 and "standalone simulator must not import pydantic" in result.stderr


def test_frontend_checker_detects_escape():
    inside = FRONTEND_SRC / "lib" / "api" / "client.ts"
    assert _escapes_frontend(inside, "../../../../src/models/api")
    assert not _escapes_frontend(inside, "./schema")
    assert not _escapes_frontend(inside, "@/lib/env")
    assert _TS_IMPORT.findall('import x from "../../../../src/a";\nconst y = await import("./b");') == [
        "../../../../src/a",
        "./b",
    ]
