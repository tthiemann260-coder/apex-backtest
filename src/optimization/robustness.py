"""
robustness.py — Robustness Report (OPT-04).

Combines Walk-Forward Efficiency, Monte Carlo percentiles, and Parameter
Stability into a single summary report with pass/fail assessment.

Pass criteria:
- WFO Efficiency > 0.5
- MC p5 equity > initial equity (strategy beats random shuffling at 5th percentile)
- Parameter Stability > 0.5

Requirement: OPT-04
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from src.optimization.walk_forward import WFOResult
from src.optimization.monte_carlo import MCResult
from src.optimization.sensitivity import SensitivityResult


@dataclass(frozen=True)
class RobustnessReport:
    """Aggregated robustness assessment."""
    # Walk-Forward
    wfo_efficiency: float
    wfo_mean_oos_sharpe: float
    wfo_n_windows: int
    wfo_pass: bool

    # Monte Carlo
    mc_p5_equity: float
    mc_p95_equity: float
    mc_equity_percentile: float
    mc_n_trades: int
    mc_pass: bool

    # Sensitivity
    sensitivity_overall: float
    sensitivity_param_cv: dict[str, float]
    sensitivity_pass: bool

    # Overall
    overall_pass: bool
    score: float  # 0-100 composite score


def compute_robustness(
    wfo: WFOResult,
    mc: MCResult,
    sensitivity: SensitivityResult,
    initial_equity: Decimal = Decimal("10000"),
    wfo_threshold: float = 0.5,
    mc_threshold: float = 0.0,
    stability_threshold: float = 0.5,
) -> RobustnessReport:
    """Compute robustness report from component results.

    Parameters
    ----------
    wfo : WFOResult
        Walk-forward validation results.
    mc : MCResult
        Monte Carlo simulation results.
    sensitivity : SensitivityResult
        Parameter sensitivity results.
    initial_equity : Decimal
        Initial portfolio equity for MC comparison.
    wfo_threshold : float
        Minimum WFO efficiency to pass. Default: 0.5.
    mc_threshold : float
        MC p5 equity must exceed initial_equity * (1 + threshold). Default: 0.0.
    stability_threshold : float
        Minimum parameter stability. Default: 0.5.

    Returns
    -------
    RobustnessReport
        Pass/fail assessment with composite score.
    """
    init_eq = float(initial_equity)

    # WFO assessment
    wfo_eff = wfo.mean_efficiency
    wfo_pass = wfo_eff >= wfo_threshold and len(wfo.windows) > 0

    # MC assessment
    mc_pass_val = mc.p5_equity >= init_eq * (1 + mc_threshold) if mc.n_trades >= 2 else False

    # Sensitivity assessment
    sens_pass = sensitivity.overall_stability >= stability_threshold

    # Overall
    overall = wfo_pass and mc_pass_val and sens_pass

    # Composite score (0-100)
    # WFO: 0-33 based on efficiency (0-1 range)
    wfo_score = min(33.0, max(0.0, wfo_eff * 33.0))

    # MC: 0-33 based on equity percentile
    mc_score = min(33.0, max(0.0, mc.equity_percentile / 100.0 * 33.0))

    # Sensitivity: 0-34 based on stability
    sens_score = min(34.0, max(0.0, sensitivity.overall_stability * 34.0))

    score = wfo_score + mc_score + sens_score

    return RobustnessReport(
        wfo_efficiency=wfo_eff,
        wfo_mean_oos_sharpe=wfo.mean_oos_sharpe,
        wfo_n_windows=len(wfo.windows),
        wfo_pass=wfo_pass,
        mc_p5_equity=mc.p5_equity,
        mc_p95_equity=mc.p95_equity,
        mc_equity_percentile=mc.equity_percentile,
        mc_n_trades=mc.n_trades,
        mc_pass=mc_pass_val,
        sensitivity_overall=sensitivity.overall_stability,
        sensitivity_param_cv=dict(sensitivity.param_cv),
        sensitivity_pass=sens_pass,
        overall_pass=overall,
        score=score,
    )
