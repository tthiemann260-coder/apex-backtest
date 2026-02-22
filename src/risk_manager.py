"""
risk_manager.py — Advanced risk management for apex-backtest.

Provides:
- RiskManager: Central orchestrator for position sizing and trade gating (RISK-01)
- Fixed Fractional Sizing: ATR-based stop distance (RISK-02)
- KellyCriterion: Adaptive sizing from rolling trade history (RISK-03)
- PortfolioHeatMonitor: Total open risk tracking (RISK-04)
- DrawdownScaler: Position size reduction during drawdowns (RISK-05)
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from src.events import FillEvent, MarketEvent, OrderSide


# ---------------------------------------------------------------------------
# Kelly Criterion (RISK-03)
# ---------------------------------------------------------------------------

class KellyCriterion:
    """Adaptive position sizing from rolling trade history.

    Parameters
    ----------
    lookback : int
        Rolling window of round-trip trades (default 40).
    fraction : Decimal
        Kelly fraction — 0.5 = Half-Kelly (default).
    min_trades : int
        Minimum trades before Kelly activates (default 20).
    max_kelly_pct : Decimal
        Cap output at this fraction of equity (default 0.05 = 5%).
    """

    def __init__(
        self,
        lookback: int = 40,
        fraction: Decimal = Decimal("0.5"),
        min_trades: int = 20,
        max_kelly_pct: Decimal = Decimal("0.05"),
    ) -> None:
        self._lookback = lookback
        self._fraction = fraction
        self._min_trades = min_trades
        self._max_kelly_pct = max_kelly_pct
        self._win_rate: Decimal = Decimal("0")
        self._win_loss_ratio: Decimal = Decimal("0")
        self._trade_count: int = 0

    def update(self, fill_log: list[FillEvent]) -> None:
        """Extract round-trip PnLs from fill_log and compute stats."""
        pnls = self._extract_round_trip_pnls(fill_log)
        if not pnls:
            self._trade_count = 0
            return

        # Use last N round-trips
        recent = pnls[-self._lookback:]
        self._trade_count = len(recent)

        wins = [p for p in recent if p > Decimal("0")]
        losses = [p for p in recent if p <= Decimal("0")]

        total = len(recent)
        self._win_rate = Decimal(str(len(wins))) / Decimal(str(total))

        avg_win = sum(wins) / Decimal(str(len(wins))) if wins else Decimal("0")
        avg_loss = abs(sum(losses) / Decimal(str(len(losses)))) if losses else Decimal("1")

        self._win_loss_ratio = avg_win / avg_loss if avg_loss > 0 else Decimal("0")

    def kelly_fraction(self) -> Optional[Decimal]:
        """Return adjusted Kelly fraction, or None if not enough trades."""
        if self._trade_count < self._min_trades:
            return None

        if self._win_loss_ratio == Decimal("0"):
            return Decimal("0")

        # Kelly: W - (1-W)/R
        kelly = self._win_rate - (Decimal("1") - self._win_rate) / self._win_loss_ratio
        adjusted = kelly * self._fraction

        # Floor at 0, cap at max
        if adjusted < Decimal("0"):
            return Decimal("0")
        if adjusted > self._max_kelly_pct:
            return self._max_kelly_pct

        return adjusted

    @staticmethod
    def _extract_round_trip_pnls(fill_log: list[FillEvent]) -> list[Decimal]:
        """Extract PnLs from fill pairs (open + close)."""
        pnls: list[Decimal] = []
        open_fills: dict[str, list[FillEvent]] = {}

        for fill in fill_log:
            symbol = fill.symbol
            if symbol not in open_fills:
                open_fills[symbol] = []

            stack = open_fills[symbol]
            if not stack:
                stack.append(fill)
            elif stack[0].side == fill.side:
                # Same direction — adding to position
                stack.append(fill)
            else:
                # Opposite direction — closing
                open_fill = stack.pop(0)
                if open_fill.side == OrderSide.BUY:
                    pnl = (fill.fill_price - open_fill.fill_price) * min(
                        open_fill.quantity, fill.quantity,
                    )
                else:
                    pnl = (open_fill.fill_price - fill.fill_price) * min(
                        open_fill.quantity, fill.quantity,
                    )
                pnl -= fill.commission + open_fill.commission
                pnls.append(pnl)

        return pnls


# ---------------------------------------------------------------------------
# Portfolio Heat Monitor (RISK-04)
# ---------------------------------------------------------------------------

class PortfolioHeatMonitor:
    """Tracks total open risk across all positions.

    Parameters
    ----------
    max_heat_pct : Decimal
        Maximum portfolio heat as fraction of equity (default 0.06 = 6%).
    atr_multiplier : Decimal
        Multiplier for ATR-based stop distance estimation.
    """

    def __init__(
        self,
        max_heat_pct: Decimal = Decimal("0.06"),
        atr_multiplier: Decimal = Decimal("2.0"),
    ) -> None:
        self._max_heat_pct = max_heat_pct
        self._atr_multiplier = atr_multiplier

    def compute_heat(self, portfolio, strategy, prices: dict[str, Decimal]) -> Decimal:
        """Compute current portfolio heat as fraction of equity."""
        equity = portfolio.compute_equity(prices)
        if equity <= Decimal("0"):
            return Decimal("0")

        atr = getattr(strategy, "current_atr", Decimal("0"))
        stop_distance = atr * self._atr_multiplier if atr > 0 else Decimal("0")

        total_risk = Decimal("0")
        for symbol, pos in portfolio.positions.items():
            if pos.quantity <= Decimal("0"):
                continue
            if stop_distance > 0:
                total_risk += pos.quantity * stop_distance
            else:
                # Fallback: 2% of position value
                price = prices.get(symbol, pos.avg_entry_price)
                total_risk += pos.quantity * price * Decimal("0.02")

        return total_risk / equity

    def can_add_risk(
        self,
        portfolio,
        strategy,
        prices: dict[str, Decimal],
        new_risk: Decimal,
    ) -> bool:
        """Check if adding new_risk would exceed heat limit."""
        equity = portfolio.compute_equity(prices)
        if equity <= Decimal("0"):
            return False

        current_heat = self.compute_heat(portfolio, strategy, prices)
        additional_heat = new_risk / equity
        return current_heat + additional_heat <= self._max_heat_pct


# ---------------------------------------------------------------------------
# Drawdown Scaler (RISK-05)
# ---------------------------------------------------------------------------

class DrawdownScaler:
    """Reduces position size linearly during drawdowns.

    Parameters
    ----------
    max_drawdown_pct : Decimal
        Drawdown threshold where scaling begins (default 0.05 = 5%).
    full_stop_pct : Decimal
        Drawdown where position size hits min_scale (default 0.20 = 20%).
    min_scale : Decimal
        Minimum scaling factor (default 0.25 = 25% of normal size).
    """

    def __init__(
        self,
        max_drawdown_pct: Decimal = Decimal("0.05"),
        full_stop_pct: Decimal = Decimal("0.20"),
        min_scale: Decimal = Decimal("0.25"),
    ) -> None:
        self._max_drawdown_pct = max_drawdown_pct
        self._full_stop_pct = full_stop_pct
        self._min_scale = min_scale

    def compute_scale(self, equity_log: list[dict]) -> Decimal:
        """Compute position scale factor based on current drawdown."""
        if not equity_log:
            return Decimal("1")

        peak = Decimal("0")
        for entry in equity_log:
            eq = entry["equity"]
            if eq > peak:
                peak = eq

        if peak <= Decimal("0"):
            return Decimal("1")

        current = equity_log[-1]["equity"]
        dd = (peak - current) / peak

        if dd <= self._max_drawdown_pct:
            return Decimal("1")

        if dd >= self._full_stop_pct:
            return self._min_scale

        # Linear interpolation
        range_size = self._full_stop_pct - self._max_drawdown_pct
        if range_size <= Decimal("0"):
            return self._min_scale

        progress = (dd - self._max_drawdown_pct) / range_size
        scale = Decimal("1") - progress * (Decimal("1") - self._min_scale)
        return scale


# ---------------------------------------------------------------------------
# RiskManager (RISK-01, RISK-02)
# ---------------------------------------------------------------------------

class RiskManager:
    """Central risk orchestrator for position sizing and trade gating.

    Parameters
    ----------
    risk_per_trade : Decimal
        Max risk per trade as fraction of equity (default 0.01 = 1%).
    atr_multiplier : Decimal
        ATR multiplier for stop distance (default 2.0).
    fallback_risk_pct : Decimal
        Fallback stop as pct of price if ATR unavailable (default 0.02 = 2%).
    max_position_pct : Decimal
        Max single position as pct of equity (default 0.20 = 20%).
    max_concurrent_positions : int
        Max number of open positions (default 5).
    kelly : Optional[KellyCriterion]
        Kelly Criterion module for adaptive sizing.
    heat_monitor : Optional[PortfolioHeatMonitor]
        Portfolio heat tracking module.
    dd_scaler : Optional[DrawdownScaler]
        Drawdown-based position scaling module.
    """

    def __init__(
        self,
        risk_per_trade: Decimal = Decimal("0.01"),
        atr_multiplier: Decimal = Decimal("2.0"),
        fallback_risk_pct: Decimal = Decimal("0.02"),
        max_position_pct: Decimal = Decimal("0.20"),
        max_concurrent_positions: int = 5,
        kelly: Optional[KellyCriterion] = None,
        heat_monitor: Optional[PortfolioHeatMonitor] = None,
        dd_scaler: Optional[DrawdownScaler] = None,
        per_asset_max_positions: Optional[dict[str, int]] = None,
        per_asset_max_pct: Optional[dict[str, Decimal]] = None,
    ) -> None:
        self._risk_per_trade = risk_per_trade
        self._atr_multiplier = atr_multiplier
        self._fallback_risk_pct = fallback_risk_pct
        self._max_position_pct = max_position_pct
        self._max_concurrent_positions = max_concurrent_positions
        self._kelly = kelly
        self._heat_monitor = heat_monitor
        self._dd_scaler = dd_scaler
        self._per_asset_max_positions = per_asset_max_positions
        self._per_asset_max_pct = per_asset_max_pct

    # ------------------------------------------------------------------
    # Trade gating
    # ------------------------------------------------------------------

    def can_trade(self, portfolio, bar: MarketEvent) -> tuple[bool, str]:
        """Check if a new trade is allowed.

        Returns (is_allowed, reason).
        """
        # Check max concurrent positions
        open_count = sum(
            1 for pos in portfolio.positions.values()
            if pos.quantity > Decimal("0")
        )
        if open_count >= self._max_concurrent_positions:
            return False, "Max concurrent positions reached"

        # Per-asset position check (MULTI-04)
        if self._per_asset_max_positions is not None:
            symbol = bar.symbol
            symbol_limit = self._per_asset_max_positions.get(symbol)
            if symbol_limit is not None:
                symbol_positions = sum(
                    1 for s, pos in portfolio.positions.items()
                    if s == symbol and pos.quantity > Decimal("0")
                )
                if symbol_positions >= symbol_limit:
                    return False, f"Per-asset limit reached for {symbol}"

        return True, "OK"

    # ------------------------------------------------------------------
    # Position sizing
    # ------------------------------------------------------------------

    def compute_quantity(
        self,
        portfolio,
        strategy,
        bar: MarketEvent,
    ) -> Decimal:
        """Compute position quantity based on risk parameters.

        Pipeline:
        1. Get equity
        2. Get ATR → stop distance (or fallback)
        3. Kelly override (if active and enough trades)
        4. risk_amount = equity * risk_per_trade
        5. raw_quantity = risk_amount / stop_distance
        6. Cap at max_position_pct
        7. Drawdown scaling
        8. Round down to integer
        """
        # Step 1: Equity
        equity_log = portfolio.equity_log
        equity = equity_log[-1]["equity"] if equity_log else portfolio.cash
        if equity <= Decimal("0"):
            return Decimal("0")

        # Step 2: ATR-based stop distance
        atr = getattr(strategy, "current_atr", Decimal("0"))
        if atr > Decimal("0"):
            stop_distance = atr * self._atr_multiplier
        else:
            # Fallback: percentage of price
            stop_distance = bar.close * self._fallback_risk_pct

        if stop_distance <= Decimal("0") or bar.close <= Decimal("0"):
            return Decimal("0")

        # Step 3: Kelly override
        risk_per_trade = self._risk_per_trade
        if self._kelly is not None:
            self._kelly.update(portfolio.fill_log)
            kelly_frac = self._kelly.kelly_fraction()
            if kelly_frac is not None:
                risk_per_trade = kelly_frac

        # Step 4: Risk amount
        risk_amount = equity * risk_per_trade

        # Step 5: Raw quantity
        quantity = risk_amount / stop_distance

        # Step 6: Cap at max position pct
        max_quantity = (equity * self._max_position_pct) / bar.close
        quantity = min(quantity, max_quantity)

        # Step 6b: Per-asset max pct cap (MULTI-04)
        if self._per_asset_max_pct is not None:
            asset_limit = self._per_asset_max_pct.get(bar.symbol)
            if asset_limit is not None:
                asset_max_qty = (equity * asset_limit) / bar.close
                quantity = min(quantity, asset_max_qty)

        # Step 7: Drawdown scaling
        if self._dd_scaler is not None:
            scale = self._dd_scaler.compute_scale(equity_log)
            quantity = quantity * scale

        # Step 8: Round down to integer
        int_qty = int(quantity)
        if int_qty < 0:
            return Decimal("0")
        return Decimal(str(int_qty))
