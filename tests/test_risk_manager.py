"""
test_risk_manager.py — Tests for Phase 16: Advanced Risk Management.

Covers:
- RiskManager core (compute_quantity, can_trade, ATR-based sizing, fallback, caps)
- KellyCriterion (warmup, 100% wins, 50/50, half-kelly, rolling lookback)
- PortfolioHeatMonitor (compute_heat, can_add_risk, empty portfolio)
- DrawdownScaler (no DD, at threshold, at full_stop, interpolation, empty log)
- Engine integration (RiskManager vs legacy, backward compat)

Requirement: TEST-22
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

import pytest

from src.events import MarketEvent, SignalEvent, SignalType, FillEvent, OrderSide
from src.portfolio import Portfolio
from src.strategy.base import BaseStrategy
from src.risk_manager import (
    RiskManager,
    KellyCriterion,
    PortfolioHeatMonitor,
    DrawdownScaler,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BASE_TS = datetime(2024, 1, 15, 10, 0, 0)


def _make_bar(
    close, high=None, low=None, open_=None, idx=0,
    symbol="TEST", volume=1000, tf="1h",
) -> MarketEvent:
    """Create a MarketEvent with Decimal prices."""
    c = Decimal(str(close))
    h = Decimal(str(high)) if high is not None else c + Decimal("1")
    l = Decimal(str(low)) if low is not None else c - Decimal("1")
    o = Decimal(str(open_)) if open_ is not None else c
    return MarketEvent(
        symbol=symbol,
        timestamp=BASE_TS + timedelta(hours=idx),
        open=o, high=h, low=l, close=c,
        volume=volume, timeframe=tf,
    )


def _make_fill(
    side, quantity, fill_price, day=15,
    symbol="TEST", commission="0",
) -> FillEvent:
    """Create a FillEvent with Decimal values."""
    return FillEvent(
        symbol=symbol,
        timestamp=BASE_TS + timedelta(days=day),
        side=OrderSide(side),
        quantity=Decimal(str(quantity)),
        fill_price=Decimal(str(fill_price)),
        commission=Decimal(str(commission)),
        slippage=Decimal("0"),
        spread_cost=Decimal("0"),
    )


def _make_portfolio(initial_cash="10000", fills=None) -> Portfolio:
    """Create a Portfolio pre-loaded with fills."""
    p = Portfolio(initial_cash=Decimal(str(initial_cash)))
    for f in (fills or []):
        p.process_fill(f)
    return p


class _MockATRStrategy(BaseStrategy):
    """Mock strategy with configurable current_atr."""

    def __init__(self, atr_value: str = "0") -> None:
        super().__init__(symbol="TEST", timeframe="1h")
        self._atr = Decimal(str(atr_value))

    @property
    def current_atr(self) -> Decimal:
        return self._atr

    def calculate_signals(self, event: MarketEvent) -> Optional[SignalEvent]:
        self.update_buffer(event)
        return None


class _MockNoATRStrategy(BaseStrategy):
    """Mock strategy without current_atr property."""

    def __init__(self) -> None:
        super().__init__(symbol="TEST", timeframe="1h")

    def calculate_signals(self, event: MarketEvent) -> Optional[SignalEvent]:
        self.update_buffer(event)
        return None


# ---------------------------------------------------------------------------
# TestRiskManagerCore
# ---------------------------------------------------------------------------

class TestRiskManagerCore:
    """Tests for RiskManager core functionality (RISK-01, RISK-02)."""

    def test_compute_quantity_basic(self):
        """Basic ATR-based sizing: 1% risk, ATR=2, mult=2 → stop=4."""
        rm = RiskManager(risk_per_trade=Decimal("0.01"), atr_multiplier=Decimal("2.0"))
        portfolio = _make_portfolio("10000")
        bar = _make_bar(100, idx=0)
        # Force an equity log entry
        portfolio.update_equity(bar)
        strategy = _MockATRStrategy("2.0")

        qty = rm.compute_quantity(portfolio, strategy, bar)
        # risk = 10000 * 0.01 = 100, stop = 2.0 * 2.0 = 4.0
        # raw qty = 100 / 4 = 25
        # max qty = 10000 * 0.20 / 100 = 20 → capped
        assert qty == Decimal("20")

    def test_atr_based_sizing(self):
        """ATR-based sizing with small ATR gives larger quantity."""
        rm = RiskManager(
            risk_per_trade=Decimal("0.01"),
            atr_multiplier=Decimal("2.0"),
            max_position_pct=Decimal("0.50"),  # high cap
        )
        portfolio = _make_portfolio("10000")
        bar = _make_bar(100, idx=0)
        portfolio.update_equity(bar)
        strategy = _MockATRStrategy("0.5")

        qty = rm.compute_quantity(portfolio, strategy, bar)
        # risk = 100, stop = 0.5 * 2.0 = 1.0, raw qty = 100
        # max qty = 10000 * 0.50 / 100 = 50 → capped
        assert qty == Decimal("50")

    def test_fallback_when_no_atr(self):
        """Fallback to price * fallback_risk_pct when no ATR."""
        rm = RiskManager(
            risk_per_trade=Decimal("0.01"),
            fallback_risk_pct=Decimal("0.02"),
            max_position_pct=Decimal("0.50"),
        )
        portfolio = _make_portfolio("10000")
        bar = _make_bar(100, idx=0)
        portfolio.update_equity(bar)
        strategy = _MockNoATRStrategy()

        qty = rm.compute_quantity(portfolio, strategy, bar)
        # stop = 100 * 0.02 = 2.0, risk = 100, raw qty = 50
        assert qty == Decimal("50")

    def test_max_position_pct_cap(self):
        """Quantity is capped by max_position_pct."""
        rm = RiskManager(
            risk_per_trade=Decimal("0.10"),  # Very high risk
            atr_multiplier=Decimal("1.0"),
            max_position_pct=Decimal("0.10"),  # But tight cap
        )
        portfolio = _make_portfolio("10000")
        bar = _make_bar(100, idx=0)
        portfolio.update_equity(bar)
        strategy = _MockATRStrategy("0.1")

        qty = rm.compute_quantity(portfolio, strategy, bar)
        # risk = 1000, stop = 0.1, raw qty = 10000 (huge)
        # max qty = 10000 * 0.10 / 100 = 10 → capped
        assert qty == Decimal("10")

    def test_zero_price_returns_zero(self):
        """Zero close price → zero quantity."""
        rm = RiskManager()
        portfolio = _make_portfolio("10000")
        bar = _make_bar(0, high=0, low=0, open_=0, idx=0)
        portfolio.update_equity(bar)
        strategy = _MockATRStrategy("1.0")

        qty = rm.compute_quantity(portfolio, strategy, bar)
        assert qty == Decimal("0")

    def test_can_trade_max_concurrent(self):
        """can_trade blocks when max concurrent positions reached."""
        rm = RiskManager(max_concurrent_positions=1)
        portfolio = _make_portfolio("10000")
        # Open a position
        buy = _make_fill("BUY", 10, 100, day=1)
        portfolio.process_fill(buy)
        bar = _make_bar(100, idx=0)

        can, reason = rm.can_trade(portfolio, bar)
        assert can is False
        assert "Max concurrent" in reason

    def test_can_trade_allows_when_below_limit(self):
        """can_trade allows when under max concurrent positions."""
        rm = RiskManager(max_concurrent_positions=5)
        portfolio = _make_portfolio("10000")
        bar = _make_bar(100, idx=0)

        can, reason = rm.can_trade(portfolio, bar)
        assert can is True


# ---------------------------------------------------------------------------
# TestKellyCriterion
# ---------------------------------------------------------------------------

class TestKellyCriterion:
    """Tests for KellyCriterion (RISK-03)."""

    def test_warmup_returns_none(self):
        """With fewer than min_trades, kelly_fraction returns None."""
        kelly = KellyCriterion(min_trades=20)
        # Only 2 round-trips
        fills = [
            _make_fill("BUY", 10, 100, day=1),
            _make_fill("SELL", 10, 110, day=2),
            _make_fill("BUY", 10, 100, day=3),
            _make_fill("SELL", 10, 105, day=4),
        ]
        kelly.update(fills)
        assert kelly.kelly_fraction() is None

    def test_100_pct_wins_capped(self):
        """100% win rate is capped at max_kelly_pct."""
        kelly = KellyCriterion(min_trades=2, max_kelly_pct=Decimal("0.05"))
        fills = []
        for i in range(10):
            fills.append(_make_fill("BUY", 10, 100, day=i * 2))
            fills.append(_make_fill("SELL", 10, 110, day=i * 2 + 1))
        kelly.update(fills)
        frac = kelly.kelly_fraction()
        assert frac is not None
        assert frac <= Decimal("0.05")

    def test_50_50_ratio_returns_zero(self):
        """50% win rate with 1:1 ratio → Kelly = 0."""
        kelly = KellyCriterion(min_trades=4, fraction=Decimal("1.0"))
        fills = []
        # 2 wins (+10 each)
        for i in range(2):
            fills.append(_make_fill("BUY", 10, 100, day=i * 2))
            fills.append(_make_fill("SELL", 10, 110, day=i * 2 + 1))
        # 2 losses (-10 each)
        for i in range(2, 4):
            fills.append(_make_fill("BUY", 10, 110, day=i * 2))
            fills.append(_make_fill("SELL", 10, 100, day=i * 2 + 1))
        kelly.update(fills)
        frac = kelly.kelly_fraction()
        assert frac is not None
        assert frac == Decimal("0")

    def test_half_kelly_scaling(self):
        """Half-Kelly reduces the raw Kelly fraction by 50%."""
        kelly_full = KellyCriterion(min_trades=2, fraction=Decimal("1.0"), max_kelly_pct=Decimal("1.0"))
        kelly_half = KellyCriterion(min_trades=2, fraction=Decimal("0.5"), max_kelly_pct=Decimal("1.0"))

        fills = []
        # High win rate
        for i in range(8):
            fills.append(_make_fill("BUY", 10, 100, day=i * 2))
            fills.append(_make_fill("SELL", 10, 120, day=i * 2 + 1))
        for i in range(8, 10):
            fills.append(_make_fill("BUY", 10, 100, day=i * 2))
            fills.append(_make_fill("SELL", 10, 95, day=i * 2 + 1))

        kelly_full.update(fills)
        kelly_half.update(fills)

        full_frac = kelly_full.kelly_fraction()
        half_frac = kelly_half.kelly_fraction()
        assert full_frac is not None and half_frac is not None
        # Half Kelly should be ~50% of full Kelly
        assert half_frac < full_frac

    def test_update_from_fill_log(self):
        """update() processes fill_log correctly."""
        kelly = KellyCriterion(min_trades=1)
        fills = [
            _make_fill("BUY", 10, 100, day=1),
            _make_fill("SELL", 10, 150, day=2),
        ]
        kelly.update(fills)
        frac = kelly.kelly_fraction()
        assert frac is not None
        assert frac > Decimal("0")

    def test_negative_kelly_returns_zero(self):
        """All losses → Kelly is negative → clamped to 0."""
        kelly = KellyCriterion(min_trades=2, fraction=Decimal("1.0"))
        fills = []
        for i in range(5):
            fills.append(_make_fill("BUY", 10, 100, day=i * 2))
            fills.append(_make_fill("SELL", 10, 80, day=i * 2 + 1))
        kelly.update(fills)
        frac = kelly.kelly_fraction()
        assert frac is not None
        assert frac == Decimal("0")


# ---------------------------------------------------------------------------
# TestPortfolioHeatMonitor
# ---------------------------------------------------------------------------

class TestPortfolioHeatMonitor:
    """Tests for PortfolioHeatMonitor (RISK-04)."""

    def test_compute_heat_with_position(self):
        """Heat is computed from position risk / equity."""
        monitor = PortfolioHeatMonitor(
            max_heat_pct=Decimal("0.10"),
            atr_multiplier=Decimal("2.0"),
        )
        portfolio = _make_portfolio("10000")
        buy = _make_fill("BUY", 10, 100, day=1)
        portfolio.process_fill(buy)
        strategy = _MockATRStrategy("2.0")
        prices = {"TEST": Decimal("100")}

        heat = monitor.compute_heat(portfolio, strategy, prices)
        # position risk = 10 * (2.0 * 2.0) = 40
        # equity = 10000 - 1000 + 10*(100-100) = 9000 (approx with cash)
        assert heat > Decimal("0")

    def test_can_add_risk_allows(self):
        """can_add_risk allows when within limit."""
        monitor = PortfolioHeatMonitor(max_heat_pct=Decimal("0.50"))
        portfolio = _make_portfolio("10000")
        strategy = _MockATRStrategy("1.0")
        prices = {"TEST": Decimal("100")}

        result = monitor.can_add_risk(portfolio, strategy, prices, Decimal("100"))
        assert result is True

    def test_can_add_risk_blocks(self):
        """can_add_risk blocks when exceeding limit."""
        monitor = PortfolioHeatMonitor(max_heat_pct=Decimal("0.01"))
        portfolio = _make_portfolio("10000")
        strategy = _MockATRStrategy("1.0")
        prices = {"TEST": Decimal("100")}

        # Try to add 200 risk to 10000 equity = 2% > 1% limit
        result = monitor.can_add_risk(portfolio, strategy, prices, Decimal("200"))
        assert result is False

    def test_empty_portfolio_zero_heat(self):
        """Empty portfolio has zero heat."""
        monitor = PortfolioHeatMonitor()
        portfolio = _make_portfolio("10000")
        strategy = _MockATRStrategy("1.0")
        prices = {"TEST": Decimal("100")}

        heat = monitor.compute_heat(portfolio, strategy, prices)
        assert heat == Decimal("0")

    def test_heat_with_multiple_positions(self):
        """Heat sums risk across all positions."""
        monitor = PortfolioHeatMonitor(atr_multiplier=Decimal("2.0"))
        portfolio = _make_portfolio("100000")
        buy1 = _make_fill("BUY", 10, 100, day=1, symbol="A")
        buy2 = _make_fill("BUY", 20, 50, day=2, symbol="B")
        portfolio.process_fill(buy1)
        portfolio.process_fill(buy2)
        strategy = _MockATRStrategy("1.0")
        prices = {"A": Decimal("100"), "B": Decimal("50")}

        heat = monitor.compute_heat(portfolio, strategy, prices)
        # A: 10 * 2.0 = 20, B: 20 * 2.0 = 40 → total 60
        # equity ≈ 100000 - 1000 - 1000 = 98000
        assert heat > Decimal("0")


# ---------------------------------------------------------------------------
# TestDrawdownScaler
# ---------------------------------------------------------------------------

class TestDrawdownScaler:
    """Tests for DrawdownScaler (RISK-05)."""

    def test_no_drawdown_full_scale(self):
        """No drawdown → scale = 1.0."""
        scaler = DrawdownScaler()
        equity_log = [
            {"equity": Decimal("10000"), "timestamp": BASE_TS},
            {"equity": Decimal("10500"), "timestamp": BASE_TS + timedelta(hours=1)},
        ]
        assert scaler.compute_scale(equity_log) == Decimal("1")

    def test_at_threshold_full_scale(self):
        """Drawdown exactly at max_drawdown_pct → still scale = 1.0."""
        scaler = DrawdownScaler(max_drawdown_pct=Decimal("0.05"))
        equity_log = [
            {"equity": Decimal("10000"), "timestamp": BASE_TS},
            {"equity": Decimal("9500"), "timestamp": BASE_TS + timedelta(hours=1)},
        ]
        # DD = 500/10000 = 5% = threshold
        assert scaler.compute_scale(equity_log) == Decimal("1")

    def test_at_full_stop_min_scale(self):
        """Drawdown at full_stop_pct → scale = min_scale."""
        scaler = DrawdownScaler(
            max_drawdown_pct=Decimal("0.05"),
            full_stop_pct=Decimal("0.20"),
            min_scale=Decimal("0.25"),
        )
        equity_log = [
            {"equity": Decimal("10000"), "timestamp": BASE_TS},
            {"equity": Decimal("8000"), "timestamp": BASE_TS + timedelta(hours=1)},
        ]
        # DD = 2000/10000 = 20% = full_stop
        assert scaler.compute_scale(equity_log) == Decimal("0.25")

    def test_linear_interpolation(self):
        """Drawdown between thresholds → linear interpolation."""
        scaler = DrawdownScaler(
            max_drawdown_pct=Decimal("0.10"),
            full_stop_pct=Decimal("0.20"),
            min_scale=Decimal("0.25"),
        )
        equity_log = [
            {"equity": Decimal("10000"), "timestamp": BASE_TS},
            {"equity": Decimal("8500"), "timestamp": BASE_TS + timedelta(hours=1)},
        ]
        # DD = 1500/10000 = 15%, midpoint between 10% and 20%
        # progress = (0.15 - 0.10) / (0.20 - 0.10) = 0.5
        # scale = 1 - 0.5 * (1 - 0.25) = 1 - 0.375 = 0.625
        scale = scaler.compute_scale(equity_log)
        assert scale == Decimal("0.625")

    def test_empty_equity_log_full_scale(self):
        """Empty equity log → scale = 1.0."""
        scaler = DrawdownScaler()
        assert scaler.compute_scale([]) == Decimal("1")


# ---------------------------------------------------------------------------
# TestEngineIntegration
# ---------------------------------------------------------------------------

class TestEngineIntegration:
    """Tests for RiskManager-Engine integration."""

    def test_engine_with_risk_manager_sizes_differently(self):
        """Engine with RiskManager uses risk-based sizing, not 10%."""
        from src.engine import BacktestEngine
        from src.execution import ExecutionHandler

        portfolio = Portfolio(initial_cash=Decimal("10000"))
        execution = ExecutionHandler(
            slippage_pct=Decimal("0"),
            commission_per_trade=Decimal("0"),
            commission_per_share=Decimal("0"),
            spread_pct=Decimal("0"),
        )
        rm = RiskManager(
            risk_per_trade=Decimal("0.01"),
            atr_multiplier=Decimal("2.0"),
            max_position_pct=Decimal("0.50"),
        )
        strategy = _MockATRStrategy("2.0")
        bar = _make_bar(100, idx=0)

        # Create engine with RiskManager
        from unittest.mock import MagicMock
        dh = MagicMock()
        engine = BacktestEngine(dh, strategy, portfolio, execution, risk_manager=rm)

        # Manually call sizing
        portfolio.update_equity(bar)
        qty = engine._calculate_order_quantity(bar)

        # With RM: risk=100, stop=4, raw=25, max=50 → 25
        assert qty == Decimal("25")

    def test_engine_without_risk_manager_legacy(self):
        """Engine without RiskManager uses legacy 10% sizing."""
        from src.engine import BacktestEngine
        from src.execution import ExecutionHandler

        portfolio = Portfolio(initial_cash=Decimal("10000"))
        execution = ExecutionHandler(
            slippage_pct=Decimal("0"),
            commission_per_trade=Decimal("0"),
            commission_per_share=Decimal("0"),
            spread_pct=Decimal("0"),
        )
        strategy = _MockATRStrategy("2.0")
        bar = _make_bar(100, idx=0)

        from unittest.mock import MagicMock
        dh = MagicMock()
        engine = BacktestEngine(dh, strategy, portfolio, execution)

        portfolio.update_equity(bar)
        qty = engine._calculate_order_quantity(bar)

        # Legacy: 10% of 10000 / 100 = 10
        assert qty == Decimal("10")

    def test_backward_compatibility_create_engine(self):
        """create_engine() works without risk_manager parameter."""
        from src.engine import create_engine
        from src.data_handler import DataHandler
        from unittest.mock import MagicMock

        dh = MagicMock(spec=DataHandler)
        strategy = _MockATRStrategy("1.0")

        engine = create_engine(dh, strategy)
        assert engine._risk_manager is None
