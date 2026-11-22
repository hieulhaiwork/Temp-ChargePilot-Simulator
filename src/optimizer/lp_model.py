"""FR6 — bài LP phân bổ công suất trong MỘT bước MPC (ràng buộc ba tầng của ADR-010).

Ký hiệu: k = bước LP (config.optimizer.planning_step_minutes), h[i,k] = số giờ booking i CÓ MẶT ở cổng
trong bước k (0 ngoài [plug-in/arrival, deadline) — FR9), η = power_conversion_efficiency.

  Biến
    p[i,k] ≥ 0    công suất đầu ra cổng cho booking i ở bước k (kW, trung bình trong lúc có mặt)
    u[i]   ≥ 0    điện thiếu của booking i tại deadline (kWh)
    d[i,k] ≥ 0    |p[i,k] − p[i,k−1]| — làm mượt (giảm bật-tắt, luật anti_flapping)

  Ràng buộc
    (1) Σ_i p[i,k] ≤ P_avail[k] · η                  ∀k     lưới (giảm khi sự cố) — MT4
    (1b) Σ_{i ∈ tủ c} p[i,k] ≤ cap_tủ_c;  Σ_{i ∈ vùng z} p[i,k] ≤ budget_z
    (2) p[i,k] ≤ min(P_cổng, P_xe_i), = 0 nếu h[i,k] = 0
    (3) Σ_k p[i,k]·h[i,k] + u[i] ≥ E_i ;  Σ_k p[i,k]·h[i,k] ≤ E_i    đủ kWh (cứng, FR9) và không sạc thừa
    (4) p[i,k_i] + s[i] ≥ P_min_i   xe chưa sạc phải bắt đầu trong consent.max_start_delay_minutes (FR13);
        s[i] ≥ 0 phạt λ_u·h — mềm để luôn khả thi khi nguồn giảm (xem horizon._start_requirement)

  Mục tiêu
    min  Σ price[k]·p[i,k]·h[i,k] + λ_u·Σ u[i] + ε·Σ k·p[i,k]·h[i,k] + μ·Σ d[i,k]
    λ_u = unmet_penalty_factor × giá cao nhất (điện thiếu trội tuyệt đối), ε = early_charge_factor ×
    giá thấp nhất (cùng giá thì sạc sớm), μ = smoothing_factor × giá thấp nhất — đều ở station.yaml (ADR-003).

Solver: scipy.optimize.linprog(method="highs") — HiGHS kèm trong scipy. Mục tiêu p95 ≤ 2 s (MT5).

Owner: TV1. Task: T2.1.
"""

import time
from datetime import UTC, datetime

import numpy as np
from scipy.optimize import linprog
from scipy.sparse import coo_matrix

from src.models.charging import SchedulePlan, StrategyName
from src.optimizer.assignment import Assignment
from src.optimizer.base import PlanningContext
from src.optimizer.horizon import build_grid, constraint_groups, prices, session_windows, to_session_plans


class LpSolveError(RuntimeError):
    """Solver không trả nghiệm (không nên xảy ra: bài luôn khả thi nhờ biến điện thiếu u)."""


def solve_power_allocation(ctx: PlanningContext, assignment: Assignment, strategy: StrategyName) -> SchedulePlan:
    """Dựng + giải LP ở trên cho các booking đã có đầu nối, trả SchedulePlan (version = state + 1)."""
    return solve_with_unmet(ctx, assignment, strategy)[0]


def solve_with_unmet(
    ctx: PlanningContext, assignment: Assignment, strategy: StrategyName
) -> tuple[SchedulePlan, dict[str, float]]:
    """Như solve_power_allocation, kèm booking_id → kWh thiếu tại deadline (FR4: lộ ra, không giấu)."""
    started = time.perf_counter()
    grid = build_grid(ctx)
    windows = session_windows(ctx, assignment, grid)
    n, n_steps = len(windows), len(grid)
    power = [[0.0] * n_steps for _ in range(n)]
    unmet = [0.0] * n
    if n:
        power, unmet = _solve(ctx, windows, grid)
    plan = SchedulePlan(
        version=ctx.state.schedule_version + 1,
        strategy=strategy,
        created_at=datetime.now(UTC),
        horizon_start=ctx.now,
        step_minutes=ctx.config.optimizer.planning_step_minutes,
        sessions=to_session_plans(windows, power, grid, assignment),
        queue=list(assignment.queue),
        solve_time_s=round(time.perf_counter() - started, 4),
    )
    return plan, {w.booking.booking_id: u for w, u in zip(windows, unmet, strict=True)}


def _solve(ctx: PlanningContext, windows, grid) -> tuple[list[list[float]], list[float]]:
    n, n_steps = len(windows), len(grid)
    opt = ctx.config.optimizer
    price = np.array(prices(ctx, grid))
    lam_u = opt.unmet_penalty_factor * float(price.max())
    eps = opt.early_charge_factor * float(price.min())
    mu = opt.smoothing_factor * float(price.min())

    n_p = n * n_steps
    n_d = n * max(n_steps - 1, 0)
    starts = [(i, w) for i, w in enumerate(windows) if w.start_step is not None and w.start_min_kw > 0]
    n_s = len(starts)
    n_vars = n_p + n + n_d + n_s

    def p_idx(i: int, k: int) -> int:
        return i * n_steps + k

    def u_idx(i: int) -> int:
        return n_p + i

    def d_idx(i: int, k: int) -> int:  # k ≥ 1
        return n_p + n + i * (n_steps - 1) + (k - 1)

    hours = np.array([w.hours for w in windows])  # n × n_steps
    # Xe DC rút cổng ngay khi đầy (F14): sạc xong sớm = cổng rảnh sớm cho xe đang chờ. Phạt theo bước cho riêng DC.
    dc_rate = opt.dc_turnover_factor * float(price.max())
    is_dc = np.array([1.0 if w.booking.request.zone == "DC" else 0.0 for w in windows])
    step_index = np.arange(n_steps)[None, :]
    c = np.zeros(n_vars)
    c[:n_p] = ((price[None, :] + (eps + dc_rate * is_dc[:, None]) * step_index) * hours).reshape(-1)
    c[n_p : n_p + n] = lam_u
    c[n_p + n : n_p + n + n_d] = mu
    # (4) consent lùi giờ: p[i,k_i] + s_i ≥ P_min_i — mềm để bài luôn khả thi khi nguồn bị giảm; s_i (kW thiếu
    # lúc phải bắt đầu) phạt ngang điện thiếu nên LP chỉ trễ khi thật sự không đủ công suất.
    for j, (_, w) in enumerate(starts):
        c[n_p + n + n_d + j] = lam_u * w.hours[w.start_step]

    bounds = []
    for w in windows:
        bounds += [(0.0, w.cap_kw if h > 0 else 0.0) for h in w.hours]
    bounds += [(0.0, None)] * (n + n_d + n_s)

    rows, cols, vals, rhs = [], [], [], []
    r = 0

    def add(entries, b):
        nonlocal r
        for col, v in entries:
            rows.append(r)
            cols.append(col)
            vals.append(v)
        rhs.append(b)
        r += 1

    for group in constraint_groups(ctx, windows, grid):
        for k in range(n_steps):
            members = [(p_idx(i, k), 1.0) for i in group.members if windows[i].hours[k] > 0]
            if members:
                add(members, group.limit_kw[k])
    for i, w in enumerate(windows):
        energy = [(p_idx(i, k), w.hours[k]) for k in range(n_steps) if w.hours[k] > 0]
        add([(col, -v) for col, v in energy] + [(u_idx(i), -1.0)], -w.remaining_kwh)  # đủ kWh
        if energy:
            add(energy, w.remaining_kwh)  # không sạc thừa
        for k in range(1, n_steps):
            add([(p_idx(i, k), 1.0), (p_idx(i, k - 1), -1.0), (d_idx(i, k), -1.0)], 0.0)
            add([(p_idx(i, k - 1), 1.0), (p_idx(i, k), -1.0), (d_idx(i, k), -1.0)], 0.0)
    for j, (i, w) in enumerate(starts):
        add([(p_idx(i, w.start_step), -1.0), (n_p + n + n_d + j, -1.0)], -w.start_min_kw)

    a_ub = coo_matrix((vals, (rows, cols)), shape=(r, n_vars)).tocsr()
    result = linprog(c, A_ub=a_ub, b_ub=np.array(rhs), bounds=bounds, method="highs")
    if result.status != 0:
        raise LpSolveError(f"HiGHS: {result.message}")
    x = result.x
    power = [[max(float(x[p_idx(i, k)]), 0.0) for k in range(n_steps)] for i in range(n)]
    unmet = [max(float(x[u_idx(i)]), 0.0) for i in range(n)]
    return power, unmet
