"""
sensitivity.py — Parameter Sensitivity Analysis (OPT-02).

Perturbs each strategy parameter by ±10/20/30% and measures performance
degradation. Produces data for a stability heatmap.

Key metrics:
- Coefficient of Variation (CV = std/mean): low CV = stable strategy
- Per-parameter stability scores
- Heatmap data: parameter x perturbation% → Sharpe Ratio

Requirement: OPT-02
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from src.data_handler import DataHandler
from src.engine import create_engine
from src.metrics import compute as compute_metrics


@dataclass(frozen=True)
class SensitivityPoint:
    """Single data point in the sensitivity grid."""
    param_name: str
    perturbation_pct: float  # e.g., -30, -20, -10, 0, 10, 20, 30
    param_value: float
    sharpe: float
    net_pnl: float
    win_rate: float
    max_dd_pct: float


@dataclass
class SensitivityResult:
    """Aggregate sensitivity analysis results."""
    points: list[SensitivityPoint] = field(default_factory=list)
    param_cv: dict[str, float] = field(default_factory=dict)  # CV per param
    overall_stability: float = 0.0  # avg(1 - CV), 1.0 = perfectly stable
    baseline_sharpe: float = 0.0


def _import_strategy_class(strategy_name: str):
    from src.dashboard.callbacks import STRATEGY_MAP
    module_path, class_name = STRATEGY_MAP[strategy_name]
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def run_sensitivity_analysis(
    symbol: str,
    strategy_name: str,
    base_params: dict,
    timeframe: str = "1d",
    perturbations: Optional[list[float]] = None,
    csv_path: Optional[str] = None,
    source: str = "csv",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    initial_cash: Decimal = Decimal("10000"),
) -> SensitivityResult:
    """Run parameter sensitivity analysis.

    Parameters
    ----------
    symbol : str
        Instrument symbol.
    strategy_name : str
        Strategy name.
    base_params : dict
        Baseline strategy parameters.
    timeframe : str
        Bar timeframe.
    perturbations : Optional[list[float]]
        Perturbation percentages. Default: [-30, -20, -10, 0, 10, 20, 30].
    csv_path, source, start_date, end_date : str
        DataHandler parameters.
    initial_cash : Decimal
        Starting capital.

    Returns
    -------
    SensitivityResult
        Grid of results + stability metrics.
    """
    if perturbations is None:
        perturbations = [-30.0, -20.0, -10.0, 0.0, 10.0, 20.0, 30.0]

    strategy_cls = _import_strategy_class(strategy_name)
    points: list[SensitivityPoint] = []
    baseline_sharpe = 0.0

    # Identify numeric parameters that can be perturbed
    numeric_params = {
        k: v for k, v in base_params.items()
        if isinstance(v, (int, float)) and v != 0
    }

    for param_name, base_value in numeric_params.items():
        param_sharpes: list[float] = []

        for pct in perturbations:
            multiplier = 1.0 + pct / 100.0
            new_value = base_value * multiplier

            # Build modified params
            modified_params = dict(base_params)
            if isinstance(base_value, int):
                modified_params[param_name] = max(1, int(round(new_value)))
            else:
                modified_params[param_name] = new_value

            # Run backtest
            dh = DataHandler(
                symbol=symbol,
                timeframe=timeframe,
                csv_path=csv_path,
                source=source,
                start_date=start_date,
                end_date=end_date,
            )
            strategy = strategy_cls(
                symbol=symbol, timeframe=timeframe, params=modified_params,
            )
            engine = create_engine(
                data_handler=dh,
                strategy=strategy,
                initial_cash=initial_cash,
            )
            result = engine.run()
            metrics = compute_metrics(
                equity_log=result.equity_log,
                fill_log=result.fill_log,
                timeframe=timeframe,
            )

            sharpe = float(metrics.sharpe_ratio)
            param_sharpes.append(sharpe)

            if pct == 0.0 and baseline_sharpe == 0.0:
                baseline_sharpe = sharpe

            points.append(SensitivityPoint(
                param_name=param_name,
                perturbation_pct=pct,
                param_value=float(modified_params[param_name]),
                sharpe=sharpe,
                net_pnl=float(metrics.net_pnl),
                win_rate=float(metrics.win_rate),
                max_dd_pct=float(metrics.max_drawdown_pct),
            ))

        # Compute CV for this parameter
        if param_sharpes:
            mean_s = sum(param_sharpes) / len(param_sharpes)
            if abs(mean_s) > 1e-10:
                std_s = (sum((s - mean_s) ** 2 for s in param_sharpes) / len(param_sharpes)) ** 0.5
                cv = std_s / abs(mean_s)
            else:
                cv = 1.0
        else:
            cv = 1.0

    # Build CV dict
    param_cv: dict[str, float] = {}
    for param_name in numeric_params:
        param_points = [p for p in points if p.param_name == param_name]
        sharpes = [p.sharpe for p in param_points]
        if sharpes:
            mean_s = sum(sharpes) / len(sharpes)
            if abs(mean_s) > 1e-10:
                std_s = (sum((s - mean_s) ** 2 for s in sharpes) / len(sharpes)) ** 0.5
                param_cv[param_name] = std_s / abs(mean_s)
            else:
                param_cv[param_name] = 1.0
        else:
            param_cv[param_name] = 1.0

    # Overall stability = avg(1 - CV), clamped to [0, 1]
    if param_cv:
        overall = sum(max(0.0, 1.0 - cv) for cv in param_cv.values()) / len(param_cv)
    else:
        overall = 0.0

    return SensitivityResult(
        points=points,
        param_cv=param_cv,
        overall_stability=overall,
        baseline_sharpe=baseline_sharpe,
    )
