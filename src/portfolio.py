"""
portfolio.py — Portfolio and position management for apex-backtest.

Tracks cash and positions entirely in decimal.Decimal (PORT-01).
Supports long and short positions (PORT-03).
Computes mark-to-market equity after each bar (PORT-04).
Enforces margin monitoring with simulated forced liquidation (PORT-05).
Rejects orders with insufficient capital or zero volume (PORT-06).
Uses FIFO for multi-position PnL attribution (PORT-07).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from src.events import FillEvent, MarketEvent, OrderSide


@dataclass
class Position:
    """Tracks a single position for a symbol."""
    symbol: str
    side: OrderSide
    quantity: Decimal = Decimal("0")
    avg_entry_price: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    accumulated_friction: Decimal = Decimal("0")  # Opening costs to deduct at close


class Portfolio:
    """Portfolio manager with cash, positions, and equity tracking.

    Parameters
    ----------
    initial_cash : Decimal
        Starting cash balance (default: 10000).
    margin_requirement : Decimal
        Minimum equity as fraction of position value (default: 0.25 = 25%).
    risk_per_trade : Decimal
        Maximum risk per trade as fraction of equity (default: 0.01 = 1%).
    """

    def __init__(
        self,
        initial_cash: Decimal = Decimal("10000"),
        margin_requirement: Decimal = Decimal("0.25"),
        risk_per_trade: Decimal = Decimal("0.01"),
    ) -> None:
        self._initial_cash = initial_cash
        self._cash = initial_cash
        self._margin_requirement = margin_requirement
        self._risk_per_trade = risk_per_trade
        self._positions: dict[str, Position] = {}
        self._equity_log: list[dict] = []
        self._fill_log: list[FillEvent] = []
        self._total_realized_pnl = Decimal("0")
        self._forced_liquidation_count = 0

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def cash(self) -> Decimal:
        return self._cash

    @property
    def equity_log(self) -> list[dict]:
        return list(self._equity_log)

    @property
    def fill_log(self) -> list[FillEvent]:
        return list(self._fill_log)

    @property
    def positions(self) -> dict[str, Position]:
        return dict(self._positions)

    @property
    def realized_pnl(self) -> Decimal:
        return self._total_realized_pnl

    # ------------------------------------------------------------------
    # Position sizing (PORT-02)
    # ------------------------------------------------------------------

    def calculate_position_size(
        self,
        equity: Decimal,
        stop_distance: Decimal,
        price: Decimal,
    ) -> Decimal:
        """Calculate position size based on risk percentage.

        risk_amount = equity * risk_per_trade
        position_size = risk_amount / stop_distance
        """
        if stop_distance <= Decimal("0"):
            return Decimal("0")
        risk_amount = equity * self._risk_per_trade
        return risk_amount / stop_distance

    # ------------------------------------------------------------------
    # Equity computation
    # ------------------------------------------------------------------

    def _compute_position_value(
        self, symbol: str, current_price: Decimal,
    ) -> Decimal:
        """Mark-to-market value of a position."""
        pos = self._positions.get(symbol)
        if pos is None or pos.quantity == Decimal("0"):
            return Decimal("0")

        if pos.side == OrderSide.BUY:
            # Long: value = quantity * (current - entry)
            return pos.quantity * (current_price - pos.avg_entry_price)
        else:
            # Short: value = quantity * (entry - current)
            return pos.quantity * (pos.avg_entry_price - current_price)

    def compute_equity(self, prices: dict[str, Decimal]) -> Decimal:
        """Compute total equity: cash + sum of all position values.

        Parameters
        ----------
        prices : dict[str, Decimal]
            Current prices per symbol.
        """
        total = self._cash
        for symbol, pos in self._positions.items():
            if symbol in prices and pos.quantity > Decimal("0"):
                total += self._compute_position_value(symbol, prices[symbol])
        return total

    # ------------------------------------------------------------------
    # Order validation (PORT-06)
    # ------------------------------------------------------------------

    def validate_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: Decimal,
        price: Decimal,
        bar_volume: int,
    ) -> tuple[bool, str]:
        """Validate if an order can be placed.

        Returns (is_valid, reason).
        """
        # Reject zero volume bars
        if bar_volume == 0:
            return False, "Zero volume bar — order rejected"

        # Check sufficient capital for buys
        if side == OrderSide.BUY:
            cost = quantity * price
            if cost > self._cash:
                return False, "Insufficient capital"

        return True, "OK"

    # ------------------------------------------------------------------
    # Fill processing
    # ------------------------------------------------------------------

    def process_fill(self, fill: FillEvent) -> None:
        """Process a FillEvent — update cash, positions, PnL.

        Uses FIFO for closing positions (PORT-07).
        """
        self._fill_log.append(fill)

        total_cost = fill.commission + fill.spread_cost
        symbol = fill.symbol

        if fill.side == OrderSide.BUY:
            self._process_buy(fill, total_cost)
        else:
            self._process_sell(fill, total_cost)

    def _process_buy(self, fill: FillEvent, friction: Decimal) -> None:
        """Process a BUY fill."""
        pos = self._positions.get(fill.symbol)
        cost = fill.fill_price * fill.quantity + friction

        if pos is not None and pos.side == OrderSide.SELL and pos.quantity > Decimal("0"):
            # Closing a short position (FIFO)
            close_qty = min(fill.quantity, pos.quantity)
            # PnL includes opening friction (proportional) + closing friction
            open_friction_share = (
                pos.accumulated_friction * close_qty / pos.quantity
                if pos.quantity > Decimal("0") else Decimal("0")
            )
            pnl = close_qty * (pos.avg_entry_price - fill.fill_price) - friction - open_friction_share
            self._total_realized_pnl += pnl
            pos.realized_pnl += pnl
            pos.accumulated_friction -= open_friction_share
            pos.quantity -= close_qty
            self._cash -= fill.fill_price * close_qty + friction

            remaining = fill.quantity - close_qty
            if remaining > Decimal("0"):
                self._positions[fill.symbol] = Position(
                    symbol=fill.symbol,
                    side=OrderSide.BUY,
                    quantity=remaining,
                    avg_entry_price=fill.fill_price,
                    accumulated_friction=Decimal("0"),
                )
                self._cash -= fill.fill_price * remaining
        else:
            # Opening or adding to a long position
            if pos is None or pos.quantity == Decimal("0"):
                self._positions[fill.symbol] = Position(
                    symbol=fill.symbol,
                    side=OrderSide.BUY,
                    quantity=fill.quantity,
                    avg_entry_price=fill.fill_price,
                    accumulated_friction=friction,
                )
            else:
                total_qty = pos.quantity + fill.quantity
                avg_price = (
                    (pos.avg_entry_price * pos.quantity + fill.fill_price * fill.quantity)
                    / total_qty
                )
                pos.quantity = total_qty
                pos.avg_entry_price = avg_price
                pos.accumulated_friction += friction

            self._cash -= cost

    def _process_sell(self, fill: FillEvent, friction: Decimal) -> None:
        """Process a SELL fill."""
        pos = self._positions.get(fill.symbol)
        proceeds = fill.fill_price * fill.quantity - friction

        if pos is not None and pos.side == OrderSide.BUY and pos.quantity > Decimal("0"):
            # Closing a long position (FIFO)
            close_qty = min(fill.quantity, pos.quantity)
            # PnL includes opening friction (proportional) + closing friction
            open_friction_share = (
                pos.accumulated_friction * close_qty / pos.quantity
                if pos.quantity > Decimal("0") else Decimal("0")
            )
            pnl = close_qty * (fill.fill_price - pos.avg_entry_price) - friction - open_friction_share
            self._total_realized_pnl += pnl
            pos.realized_pnl += pnl
            pos.accumulated_friction -= open_friction_share
            pos.quantity -= close_qty
            self._cash += fill.fill_price * close_qty - friction

            remaining = fill.quantity - close_qty
            if remaining > Decimal("0"):
                self._positions[fill.symbol] = Position(
                    symbol=fill.symbol,
                    side=OrderSide.SELL,
                    quantity=remaining,
                    avg_entry_price=fill.fill_price,
                    accumulated_friction=Decimal("0"),
                )
                self._cash += fill.fill_price * remaining
        else:
            # Opening or adding to a short position
            if pos is None or pos.quantity == Decimal("0"):
                self._positions[fill.symbol] = Position(
                    symbol=fill.symbol,
                    side=OrderSide.SELL,
                    quantity=fill.quantity,
                    avg_entry_price=fill.fill_price,
                    accumulated_friction=friction,
                )
            else:
                total_qty = pos.quantity + fill.quantity
                avg_price = (
                    (pos.avg_entry_price * pos.quantity + fill.fill_price * fill.quantity)
                    / total_qty
                )
                pos.quantity = total_qty
                pos.avg_entry_price = avg_price
                pos.accumulated_friction += friction

            self._cash += proceeds

    # ------------------------------------------------------------------
    # Mark-to-market equity log (PORT-04)
    # ------------------------------------------------------------------

    def update_equity(self, bar: MarketEvent) -> None:
        """Record equity after each bar."""
        prices = {bar.symbol: bar.close}
        equity = self.compute_equity(prices)
        self._equity_log.append({
            "timestamp": bar.timestamp,
            "equity": equity,
            "cash": self._cash,
            "symbol": bar.symbol,
            "price": bar.close,
        })

    # ------------------------------------------------------------------
    # Margin monitoring (PORT-05)
    # ------------------------------------------------------------------

    def check_margin(self, prices: dict[str, Decimal]) -> list[str]:
        """Check margin requirement, return symbols needing liquidation.

        Triggers when position value exceeds equity / margin_requirement.
        """
        equity = self.compute_equity(prices)
        to_liquidate: list[str] = []

        for symbol, pos in self._positions.items():
            if pos.quantity == Decimal("0"):
                continue
            if symbol not in prices:
                continue

            position_value = abs(pos.quantity * prices[symbol])
            required_equity = position_value * self._margin_requirement

            if equity < required_equity:
                to_liquidate.append(symbol)

        return to_liquidate

    def force_liquidate(
        self, symbol: str, current_price: Decimal,
    ) -> Optional[FillEvent]:
        """Force-close a position at current price (PORT-05)."""
        pos = self._positions.get(symbol)
        if pos is None or pos.quantity == Decimal("0"):
            return None

        self._forced_liquidation_count += 1

        # Create a fill to close the position
        close_side = OrderSide.SELL if pos.side == OrderSide.BUY else OrderSide.BUY
        from datetime import datetime
        fill = FillEvent(
            symbol=symbol,
            timestamp=datetime.now(),
            side=close_side,
            quantity=pos.quantity,
            fill_price=current_price,
            commission=Decimal("0"),
            slippage=Decimal("0"),
            spread_cost=Decimal("0"),
        )
        self.process_fill(fill)
        return fill
