"""ChargePilot DC charging profiles -- research/simulation model, not a BMS emulator.

Inputs/outputs:
    SOC is a fraction [0, 1]; power is kW; energy is kWh; time is minutes.
    Setpoint/port/cabinet limits describe charger output power (before battery loss).
    The caller must enforce the shared 120-kW cabinet budget across *all* ports,
    and any AC/DC site-level budget, with a separate deterministic Global Guard.

Provenance:
    VF3: VinFast usable 18.64 kWh, DC maximum 24 kW. Curve is a hypothesis.
    VF8_NEW: VinFast new generation usable 60.13 kWh, DC maximum 100 kW.
       SOC shape is a PROXY derived from EVKX older VF8 Plus 94-kWh gross/
       87.7-kWh usable curve; it is NOT a measured 2026 VF8 curve.
    VF9_123: VinFast usable 123 kWh. Vehicle max_DC is UNVERIFIED; assumed
       60-kW ceiling only for this particular 60-kW-port scenario.
    UNKNOWN: battery capacity must be supplied. Pmax default 60 kW is a
       scenario assumption, not a specification for the unidentified vehicle.
    Generic SOC shape: Simolin et al., Transportation Engineering 20 (2025)
       DOI 10.1016/j.treng.2025.100350, cubic empirical fit for mixed EVs.

Charging curves are intentionally replaceable and may be inaccurate for real
vehicles; do not use them to guarantee real-world charge completion times.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, isfinite
from typing import Literal

# (SOC fraction, relative maximum charger-output power). Hypothesized VF3 shape.
_VF3_CURVE = (
    (0.00, 0.75),
    (0.05, 1.00),
    (0.10, 0.90),
    (0.20, 0.88),
    (0.40, 0.83),
    (0.60, 0.77),
    (0.70, 0.70),
    (0.80, 0.52),
    (0.90, 0.26),
    (1.00, 0.06),
)

# Sparse anchors from the *older* EVKX VF8 Plus page, divided by its
# approximate peak 103 kW. At 100%, the source displays a non-monotonic
# 1 -> 10 kW jump (99-100%); that artifact is NOT copied into this proxy.
_VF8_OLD_SHAPE_PROXY = (
    (0.00, 1 / 103),
    (0.05, 37 / 103),
    (0.10, 74 / 103),
    (0.14, 1.00),
    (0.21, 96 / 103),
    (0.52, 96 / 103),
    (0.65, 82 / 103),
    (0.70, 82 / 103),
    (0.77, 68 / 103),
    (0.80, 59 / 103),
    (0.90, 30 / 103),
    (0.95, 14 / 103),
    (0.98, 4 / 103),
    (0.99, 1 / 103),
    (1.00, 1 / 103),
)


def _finite_nonnegative(value: float, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or value < 0:
        raise ValueError(f"{label} must be finite and nonnegative")
    return float(value)


def _fraction(value: float, label: str) -> float:
    v = _finite_nonnegative(value, label)
    if v > 1:
        raise ValueError(f"{label} must be in [0, 1]")
    return v


def _ratio(value: float, label: str) -> float:
    v = _fraction(value, label)
    if v == 0:
        raise ValueError(f"{label} must be > 0")
    return v


def _linear_curve(soc: float, points: tuple[tuple[float, float], ...]) -> float:
    if soc <= points[0][0]:
        return points[0][1]
    for (left_s, left_p), (right_s, right_p) in zip(points, points[1:]):
        if soc <= right_s:
            return left_p + (right_p - left_p) * (soc - left_s) / (right_s - left_s)
    return points[-1][1]


def _generic_heterogeneous(soc: float) -> float:
    """Empirical relative Pmax(SOC) from Simolin et al. (SOC in percent).

    This returns a dimensionless factor, NOT an absolute kW limit or a
    vehicle-specific, experimentally calibrated charging curve.
    """
    s = soc * 100
    p = (87.0 - 0.544 * s + 0.0271 * s * s - 0.000293 * s * s * s) / 100
    return max(0.0, min(1.0, p))


CurveKind = Literal["piecewise", "generic_polynomial"]


@dataclass(frozen=True)
class DCProfile:
    model: str
    usable_battery_kwh: float
    # Vehicle-side limit for this *scenario*, not necessarily an OEM-certified maximum.
    reference_max_dc_kw: float
    curve_kind: CurveKind
    curve_points: tuple[tuple[float, float], ...] = ()
    provenance: str = ""
    confidence: str = "assumed"
    reference_max_is_oem_spec: bool = False

    def __post_init__(self) -> None:
        if _finite_nonnegative(self.usable_battery_kwh, "usable_battery_kwh") == 0:
            raise ValueError("usable_battery_kwh must be > 0")
        if _finite_nonnegative(self.reference_max_dc_kw, "reference_max_dc_kw") == 0:
            raise ValueError("reference_max_dc_kw must be > 0")
        if self.curve_kind == "piecewise":
            if len(self.curve_points) < 2 or self.curve_points[0][0] != 0 or self.curve_points[-1][0] != 1:
                raise ValueError("piecewise curve must cover 0.0 through 1.0")
            last_s = -1.0
            for s, f in self.curve_points:
                _fraction(s, "curve SOC")
                _fraction(f, "curve factor")
                if s <= last_s:
                    raise ValueError("curve SOC knots must strictly increase")
                last_s = s
        elif self.curve_kind != "generic_polynomial":
            raise ValueError(f"Unsupported curve_kind: {self.curve_kind}")

    def acceptance_kw(self, soc: float) -> float:
        soc = _fraction(soc, "soc")
        factor = (
            _linear_curve(soc, self.curve_points) if self.curve_kind == "piecewise" else _generic_heterogeneous(soc)
        )
        return self.reference_max_dc_kw * factor


def resolve_dc_profile(
    model: str,
    *,
    unknown_battery_kwh: float | None = None,
    unknown_reference_max_kw: float = 60.0,
) -> DCProfile:
    """Get a fixed known profile or explicitly parameterized unknown fallback.

    'VF2' is intentionally rejected; no automatic remapping to VF3.
    """
    key = "".join(c for c in model.upper() if c.isalnum())
    if key == "VF2":
        raise ValueError("VF2 is not in the selected fleet. Did you mean VF3?")
    if key in {"VF3", "VINFASTVF3"}:
        return DCProfile(
            "VF3",
            18.64,
            24.0,
            "piecewise",
            _VF3_CURVE,
            "VinFast VF3 specs; SOC curve is a scenario hypothesis; 10-70% ~36 min is OEM reference",
            "synthetic_calibration",
            True,
        )
    if key in {"VF8", "VF8NEW", "VF82026", "VF8NEW2026", "VINFASTVF8"}:
        return DCProfile(
            "VF8_NEW_2026",
            60.13,
            100.0,
            "piecewise",
            _VF8_OLD_SHAPE_PROXY,
            "VinFast VF8 new-gen specs; proxy SOC shape from EVKX older VF8 Plus, NOT same battery",
            "cross_generation_proxy",
            True,
        )
    if key in {"VF9", "VF9123", "VINFASTVF9"}:
        return DCProfile(
            "VF9_123",
            123.0,
            60.0,
            "generic_polynomial",
            provenance="VinFast usable capacity 123 kWh; 60-kW vehicle-side reference ceiling ASSUMED for 60-kW port",
            confidence="generic_curve_vehicle_limit_assumed",
            reference_max_is_oem_spec=False,
        )
    if unknown_battery_kwh is None:
        raise ValueError(
            f"Unknown EV '{model}': provide unknown_battery_kwh (usable), and preferably unknown_reference_max_kw"
        )
    return DCProfile(
        model or "UNKNOWN",
        unknown_battery_kwh,
        unknown_reference_max_kw,
        "generic_polynomial",
        provenance="Unidentified EV; generic heterogeneous curve and scenario-assumed power ceiling",
        confidence="low_unknown_ev",
        reference_max_is_oem_spec=False,
    )


@dataclass(frozen=True)
class DCStepResult:
    soc_before: float
    soc_after: float
    requested_kw: float
    ev_acceptance_kw_at_start: float
    average_charger_output_kw: float
    charger_output_kwh: float
    battery_added_kwh: float
    grid_input_kwh: float
    average_grid_input_kw: float
    duration_minutes: float


def charge_dc_step(
    profile: DCProfile,
    *,
    soc: float,
    requested_kw: float,
    minutes: float,
    port_limit_kw: float = 60.0,
    cabinet_available_kw: float = 120.0,
    target_soc: float = 1.0,
    battery_efficiency: float = 0.95,
    charger_conversion_efficiency: float = 0.95,
    integration_seconds: float = 10.0,
) -> DCStepResult:
    """Apply an externally validated power setpoint to *one* plugged DC EV.

    Cabinet available power must be the amount reserved for THIS car by the
    coordinator; this function cannot arbitrate two ports simultaneously.
    Global Guard must enforce sum(output[port]) <= cabinet cap and site cap.
    The returned output is interval-AVERAGED, potentially below setpoint.
    """
    old_soc = _fraction(soc, "soc")
    target = _fraction(target_soc, "target_soc")
    if target < old_soc:
        raise ValueError("target_soc must be >= soc")
    p_req = _finite_nonnegative(requested_kw, "requested_kw")
    p_port = _finite_nonnegative(port_limit_kw, "port_limit_kw")
    p_cabinet = _finite_nonnegative(cabinet_available_kw, "cabinet_available_kw")
    m = _finite_nonnegative(minutes, "minutes")
    eff_b = _ratio(battery_efficiency, "battery_efficiency")
    eff_ch = _ratio(charger_conversion_efficiency, "charger_conversion_efficiency")
    h_secs = _finite_nonnegative(integration_seconds, "integration_seconds")
    if m <= 0 or h_secs <= 0:
        raise ValueError("minutes and integration_seconds must be > 0")
    # Fixed small integration substeps account for SOC taper within one minute.
    steps = ceil(m * 60 / h_secs)
    dt_h = (m / steps) / 60.0
    capacity = profile.usable_battery_kwh
    new_soc = old_soc
    output_energy = 0.0
    stored_energy = 0.0
    initial_acceptance = profile.acceptance_kw(old_soc)
    for _ in range(steps):
        if new_soc >= target - 1e-12:
            break
        p = min(p_req, p_port, p_cabinet, profile.acceptance_kw(new_soc))
        headroom_kwh = max(0.0, (target - new_soc) * capacity)
        charged_output_kwh = min(p * dt_h, headroom_kwh / eff_b)
        added_kwh = charged_output_kwh * eff_b
        output_energy += charged_output_kwh
        stored_energy += added_kwh
        new_soc = min(target, old_soc + stored_energy / capacity)
    grid_kwh = output_energy / eff_ch
    return DCStepResult(
        soc_before=old_soc,
        soc_after=new_soc,
        requested_kw=p_req,
        ev_acceptance_kw_at_start=initial_acceptance,
        average_charger_output_kw=output_energy / (m / 60),
        charger_output_kwh=output_energy,
        battery_added_kwh=stored_energy,
        grid_input_kwh=grid_kwh,
        average_grid_input_kw=grid_kwh / (m / 60),
        duration_minutes=m,
    )
