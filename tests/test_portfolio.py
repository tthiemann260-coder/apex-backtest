"""Tests for Portfolio — cash/positions, equity, margin, FIFO PnL."""

from __future__ import annotations

import pytest
from datetime import datetime
from decimal import Decimal

from src.events import FillEvent, MarketEvent, OrderSide
from src.portfolio import Portfolio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fill(
    side: OrderSide = OrderSide.BUY,
    quantity: str = "100",
    fill_price: str = "50.00",
    commission: str = "0",
    slippage: str = "0",
    spread_cost: str = "0",
    day: int = 15,
) -> FillEvent:
    return FillEvent(
        symbol="TEST",
        timestamp=datetime(2024, 1, day, 10, 0),
        side=side,
        quantity=Decimal(quantity),
        fill_price=Decimal(fill_price),
        commission=Decimal(commission),
        slippage=Decimal(slippage),
        spread_cost=Decimal(spread_cost),
    )


def _make_bar(
    close: str = "50.00",
    day: int = 15,
) -> MarketEvent:
    return MarketEvent(
        symbol="TEST",
        timestamp=datetime(2024, 1, day, 10, 0),
        open=Decimal(close),
        high=Decimal(close),
        low=Decimal(close),
        close=Decimal(close),
        volume=1000,
        timeframe="1d",
    )


# ===========================================================================
# TestCashAndPositions
# ===========================================================================

class TestCashAndPositions:
    """PORT-01: Cash + Positions in decimal.Decimal."""

    def test_initial_cash(self):
        """Portfolio starts with specified initial cash."""
        p = Portfolio(initial_cash=Decimal("10000"))
        assert p.cash == Decimal("10000")

    def test_cash_is_decimal(self):
        """Cash is always Decimal."""
        p = Portfolio()
        assert isinstance(p.cash, Decimal)

    def test_buy_reduces_cash(self):
        """Buying reduces cash by cost."""
        p = Portfolio(initial_cash=Decimal("10000"))
        fill = _make_fill(side=OrderSide.BUY, quantity="100", fill_price="50.00")
        p.process_fill(fill)
        # Cost: 100 * 50 = 5000
        assert p.cash == Decimal("5000")

    def test_sell_increases_cash(self):
        """Selling (closing long) increases cash by proceeds."""
        p = Portfolio(initial_cash=Decimal("10000"))
        # Buy first
        buy_fill = _make_fill(side=OrderSide.BUY, quantity="100", fill_price="50.00", day=15)
        p.process_fill(buy_fill)
        # Sell at higher price
        sell_fill = _make_fill(side=OrderSide.SELL, quantity="100", fill_price="52.00", day=16)
        p.process_fill(sell_fill)
        # Start: 10000, buy: -5000 = 5000, sell: +5200 = 10200
        assert p.cash == Decimal("10200")

    def test_position_tracked_after_buy(self):
        """Position is created after a buy fill."""
        p = Portfolio(initial_cash=Decimal("10000"))
        fill = _make_fill(side=OrderSide.BUY, quantity="100", fill_price="50.00")
        p.process_fill(fill)
        assert "TEST" in p.positions
        assert p.positions["TEST"].quantity == Decimal("100")


# ===========================================================================
# TestPnLAccuracy
# ===========================================================================

class TestPnLAccuracy:
    """TEST-02: PnL verification with exact Decimal equality."""

    def test_round_trip_pnl_exact(self):
        """Buy 100 at 50.00, sell at 52.00 = exactly 200.00 PnL.

        This test uses exact Decimal equality, NOT pytest.approx().
        """
        p = Portfolio(initial_cash=Decimal("10000"))
        buy = _make_fill(side=OrderSide.BUY, quantity="100", fill_price="50.00", day=15)
        sell = _make_fill(side=OrderSide.SELL, quantity="100", fill_price="52.00", day=16)
        p.process_fill(buy)
        p.process_fill(sell)

        assert p.realized_pnl == Decimal("200.00")  # EXACT, no approx

    def test_round_trip_pnl_with_commission(self):
        """PnL accounts for commissions exactly."""
        p = Portfolio(initial_cash=Decimal("10000"))
        buy = _make_fill(
            side=OrderSide.BUY, quantity="100", fill_price="50.00",
            commission="5.00", day=15,
        )
        sell = _make_fill(
            side=OrderSide.SELL, quantity="100", fill_price="52.00",
            commission="5.00", day=16,
        )
        p.process_fill(buy)
        p.process_fill(sell)

        # Gross PnL: 200, friction: 5 + 5 = 10
        assert p.realized_pnl == Decimal("190.00")

    def test_short_trade_pnl(self):
        """Short sell at 52, buy to cover at 50 = 200 PnL."""
        p = Portfolio(initial_cash=Decimal("10000"))
        sell = _make_fill(side=OrderSide.SELL, quantity="100", fill_price="52.00", day=15)
        buy = _make_fill(side=OrderSide.BUY, quantity="100", fill_price="50.00", day=16)
        p.process_fill(sell)
        p.process_fill(buy)

        assert p.realized_pnl == Decimal("200.00")


# ===========================================================================
# TestPositionSizing
# ===========================================================================

class TestPositionSizing:
    """PORT-02: Percentage-based position sizing."""

    def test_position_size_calculation(self):
        """1% risk on $10000 with 20-pip stop = correct lot size."""
        p = Portfolio(risk_per_trade=Decimal("0.01"))
        size = p.calculate_position_size(
            equity=Decimal("10000"),
            stop_distance=Decimal("0.0020"),  # 20 pips
            price=Decimal("1.2000"),
        )
        # Risk amount: 10000 * 0.01 = 100
        # Position size: 100 / 0.0020 = 50000
        assert size == Decimal("50000")

    def test_zero_stop_returns_zero(self):
        """Zero stop distance returns zero position size."""
        p = Portfolio()
        size = p.calculate_position_size(
            equity=Decimal("10000"),
            stop_distance=Decimal("0"),
            price=Decimal("100"),
        )
        assert size == Decimal("0")


# ===========================================================================
# TestEquityLog
# ===========================================================================

class TestEquityLog:
    """PORT-04: Mark-to-market equity log."""

    def test_equity_log_empty_initially(self):
        """No entries before any bar is processed."""
        p = Portfolio()
        assert len(p.equity_log) == 0

    def test_equity_log_grows_with_bars(self):
        """One entry per bar processed."""
        p = Portfolio(initial_cash=Decimal("10000"))
        for i in range(5):
            bar = _make_bar(close="50.00", day=15 + i)
            p.update_equity(bar)
        assert len(p.equity_log) == 5

    def test_equity_correct_with_position(self):
        """Equity = cash + position value."""
        p = Portfolio(initial_cash=Decimal("10000"))
        buy = _make_fill(side=OrderSide.BUY, quantity="100", fill_price="50.00")
        p.process_fill(buy)

        # Price went to 55: equity = 5000 (cash) + 100*(55-50) = 5500
        bar = _make_bar(close="55.00", day=16)
        p.update_equity(bar)

        assert p.equity_log[-1]["equity"] == Decimal("5500")


# ===========================================================================
# TestMarginMonitoring
# ===========================================================================

class TestMarginMonitoring:
    """PORT-05: Margin monitoring with forced liquidation."""

    def test_no_liquidation_when_adequate(self):
        """No liquidation needed when equity is adequate."""
        p = Portfolio(
            initial_cash=Decimal("10000"),
            margin_requirement=Decimal("0.25"),
        )
        buy = _make_fill(side=OrderSide.BUY, quantity="100", fill_price="50.00")
        p.process_fill(buy)

        to_liquidate = p.check_margin({"TEST": Decimal("50.00")})
        assert len(to_liquidate) == 0

    def test_liquidation_triggered_on_margin_call(self):
        """Liquidation triggered when equity falls below margin requirement."""
        p = Portfolio(
            initial_cash=Decimal("5100"),
            margin_requirement=Decimal("0.50"),
        )
        buy = _make_fill(side=OrderSide.BUY, quantity="100", fill_price="50.00")
        p.process_fill(buy)

        # Price drops to 40: cash=100, position value=100*(40-50)=-1000
        # Equity = 100 + (-1000) = -900
        # Required = 100*40*0.50 = 2000
        # -900 < 2000 => liquidation
        to_liquidate = p.check_margin({"TEST": Decimal("40.00")})
        assert "TEST" in to_liquidate

    def test_force_liquidate_closes_position(self):
        """Force liquidation closes the position."""
        p = Portfolio(initial_cash=Decimal("10000"))
        buy = _make_fill(side=OrderSide.BUY, quantity="100", fill_price="50.00")
        p.process_fill(buy)

        fill = p.force_liquidate("TEST", Decimal("45.00"))
        assert fill is not None
        assert p.positions["TEST"].quantity == Decimal("0")


# ===========================================================================
# TestOrderValidation
# ===========================================================================

class TestOrderValidation:
    """PORT-06: Order rejection for zero-volume and insufficient capital."""

    def test_reject_zero_volume(self):
        """Orders on zero-volume bars are rejected."""
        p = Portfolio()
        valid, reason = p.validate_order(
            "TEST", OrderSide.BUY, Decimal("100"), Decimal("50"), bar_volume=0,
        )
        assert valid is False
        assert "Zero volume" in reason

    def test_reject_insufficient_capital(self):
        """Orders exceeding available cash are rejected."""
        p = Portfolio(initial_cash=Decimal("100"))
        valid, reason = p.validate_order(
            "TEST", OrderSide.BUY, Decimal("100"), Decimal("50"), bar_volume=1000,
        )
        assert valid is False
        assert "Insufficient" in reason

    def test_accept_valid_order(self):
        """Valid orders pass validation."""
        p = Portfolio(initial_cash=Decimal("10000"))
        valid, reason = p.validate_order(
            "TEST", OrderSide.BUY, Decimal("100"), Decimal("50"), bar_volume=1000,
        )
        assert valid is True


# ===========================================================================
# TestBalanceInvariant
# ===========================================================================

class TestBalanceInvariant:
    """TEST-06: Portfolio balance invariant after every trade."""

    def test_balance_invariant_after_round_trip(self):
        """cash + position_value == initial_equity + realized_pnl."""
        p = Portfolio(initial_cash=Decimal("10000"))

        buy = _make_fill(side=OrderSide.BUY, quantity="100", fill_price="50.00", day=15)
        p.process_fill(buy)

        sell = _make_fill(side=OrderSide.SELL, quantity="100", fill_price="55.00", day=16)
        p.process_fill(sell)

        # After round trip: all positions closed
        # cash should be initial + realized PnL
        expected = Decimal("10000") + p.realized_pnl
        assert p.cash == expected

    def test_balance_invariant_with_open_position(self):
        """Equity = initial + unrealized PnL while position is open."""
        p = Portfolio(initial_cash=Decimal("10000"))

        buy = _make_fill(side=OrderSide.BUY, quantity="100", fill_price="50.00")
        p.process_fill(buy)

        # Mark-to-market at 55
        equity = p.compute_equity({"TEST": Decimal("55.00")})
        # cash: 5000, position value: 100*(55-50) = 500
        assert equity == Decimal("5500")


# ===========================================================================
# TestFIFO
# ===========================================================================

class TestFIFO:
    """PORT-07: FIFO for multi-position PnL attribution."""

    def test_partial_close_fifo(self):
        """Partial close uses FIFO: closes against earliest entry."""
        p = Portfolio(initial_cash=Decimal("20000"))

        # Buy 100 at 50
        buy1 = _make_fill(side=OrderSide.BUY, quantity="100", fill_price="50.00", day=15)
        p.process_fill(buy1)

        # Sell 50 at 55 — should close first 50 shares
        sell = _make_fill(side=OrderSide.SELL, quantity="50", fill_price="55.00", day=16)
        p.process_fill(sell)

        # PnL on 50 shares: 50 * (55 - 50) = 250
        assert p.realized_pnl == Decimal("250.00")
        # Remaining position: 50 shares
        assert p.positions["TEST"].quantity == Decimal("50")
