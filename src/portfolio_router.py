"""
portfolio_router.py — Multi-Strategy Portfolio Router (PORT-10, PORT-11).

Routes signals from multiple strategies into a single shared Portfolio,
with configurable allocation weights. Tracks per-strategy attribution.

Design:
- Single Portfolio prevents impossible leverage (shared exposure)
- Each strategy gets a weight (0.0 - 1.0) for position sizing
- Strategy Attribution tracks PnL, fills, and metrics per strategy
- Fills are tagged with strategy_name for attribution

Requirement: PORT-10, PORT-11
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from src.data_handler import DataHandler
from src.engine import BacktestResult
from src.events import (
    MarketEvent, SignalEvent, OrderEvent, FillEvent,
    SignalType, OrderType, OrderSide,
)
from src.event_queue import EventQueue
from src.execution import ExecutionHandler
from src.metrics import compute as compute_metrics, MetricsResult
from src.portfolio import Portfolio
from src.strategy.base import BaseStrategy


@dataclass
class StrategyAttribution:
    """Per-strategy performance attribution."""
    strategy_name: str
    weight: float
    fill_log: list[FillEvent] = field(default_factory=list)
    signal_count: int = 0
    order_count: int = 0
    fill_count: int = 0
    net_pnl: Decimal = Decimal("0")


@dataclass
class MultiStrategyResult:
    """Results from multi-strategy portfolio backtest."""
    equity_log: list[dict] = field(default_factory=list)
    fill_log: list[FillEvent] = field(default_factory=list)
    event_log: list = field(default_factory=list)
    final_equity: Decimal = Decimal("0")
    total_bars: int = 0
    attributions: dict[str, StrategyAttribution] = field(default_factory=dict)


class PortfolioRouter:
    """Routes signals from multiple strategies through a shared portfolio.

    Parameters
    ----------
    strategies : dict[str, BaseStrategy]
        Mapping of strategy name to strategy instance.
    weights : dict[str, float]
        Allocation weights per strategy (should sum to <= 1.0).
    data_handler : DataHandler
        Bar data source.
    initial_cash : Decimal
        Starting capital.
    slippage_pct : Decimal
        Slippage percentage.
    commission_per_trade : Decimal
        Fixed commission per trade.
    commission_per_share : Decimal
        Per-share commission.
    spread_pct : Decimal
        Bid/ask spread percentage.
    margin_requirement : Decimal
        Margin requirement fraction.
    """

    def __init__(
        self,
        strategies: dict[str, BaseStrategy],
        weights: dict[str, float],
        data_handler: DataHandler,
        initial_cash: Decimal = Decimal("10000"),
        slippage_pct: Decimal = Decimal("0.0001"),
        commission_per_trade: Decimal = Decimal("1.00"),
        commission_per_share: Decimal = Decimal("0.005"),
        spread_pct: Decimal = Decimal("0.0002"),
        margin_requirement: Decimal = Decimal("0.25"),
    ) -> None:
        self._strategies = strategies
        self._weights = weights
        self._data_handler = data_handler
        self._portfolio = Portfolio(
            initial_cash=initial_cash,
            margin_requirement=margin_requirement,
        )
        self._execution = ExecutionHandler(
            slippage_pct=slippage_pct,
            commission_per_trade=commission_per_trade,
            commission_per_share=commission_per_share,
            spread_pct=spread_pct,
        )
        self._event_log: list = []
        self._attributions: dict[str, StrategyAttribution] = {
            name: StrategyAttribution(strategy_name=name, weight=weights.get(name, 0.0))
            for name in strategies
        }
        # Track which strategy owns which position
        self._position_owner: dict[str, str] = {}  # symbol → strategy_name

    def run(self) -> MultiStrategyResult:
        """Run multi-strategy backtest."""
        total_bars = 0

        for bar in self._data_handler.stream_bars():
            total_bars += 1

            # 1. Process pending orders
            fills = self._execution.process_bar(bar)
            for fill in fills:
                self._event_log.append(fill)
                self._portfolio.process_fill(fill)
                # Attribute fill to strategy that owns the position
                owner = self._position_owner.get(fill.symbol, "")
                if owner and owner in self._attributions:
                    self._attributions[owner].fill_log.append(fill)
                    self._attributions[owner].fill_count += 1

            # 2. Check margin
            prices = {bar.symbol: bar.close}
            to_liquidate = self._portfolio.check_margin(prices)
            for symbol in to_liquidate:
                liq_fill = self._portfolio.force_liquidate(symbol, bar.close)
                if liq_fill:
                    self._event_log.append(liq_fill)

            # 3. Generate signals from all strategies
            for name, strategy in self._strategies.items():
                signal = strategy.calculate_signals(bar)
                if signal is not None:
                    self._attributions[name].signal_count += 1
                    self._event_log.append(signal)

                    order = self._signal_to_order(signal, bar, name)
                    if order is not None:
                        self._attributions[name].order_count += 1
                        self._event_log.append(order)
                        self._execution.submit_order(order)

            # 4. Update equity
            self._portfolio.update_equity(bar)

        # Compute final equity
        final_equity = Decimal("0")
        if self._portfolio.equity_log:
            final_equity = self._portfolio.equity_log[-1]["equity"]

        # Compute per-strategy PnL from attributed fills
        for attr in self._attributions.values():
            attr.net_pnl = self._compute_strategy_pnl(attr.fill_log)

        return MultiStrategyResult(
            equity_log=self._portfolio.equity_log,
            fill_log=self._portfolio.fill_log,
            event_log=self._event_log,
            final_equity=final_equity,
            total_bars=total_bars,
            attributions=self._attributions,
        )

    def _signal_to_order(
        self,
        signal: SignalEvent,
        bar: MarketEvent,
        strategy_name: str,
    ) -> Optional[OrderEvent]:
        """Convert signal to order with weight-adjusted sizing."""
        weight = Decimal(str(self._weights.get(strategy_name, 0.0)))

        if signal.signal_type == SignalType.LONG:
            quantity = self._calculate_weighted_quantity(bar, weight)
            if quantity <= Decimal("0"):
                return None
            valid, _ = self._portfolio.validate_order(
                bar.symbol, OrderSide.BUY, quantity, bar.close, bar.volume,
            )
            if not valid:
                return None
            self._position_owner[signal.symbol] = strategy_name
            return OrderEvent(
                symbol=signal.symbol,
                timestamp=signal.timestamp,
                order_type=OrderType.MARKET,
                side=OrderSide.BUY,
                quantity=quantity,
                price=None,
            )

        elif signal.signal_type == SignalType.SHORT:
            quantity = self._calculate_weighted_quantity(bar, weight)
            if quantity <= Decimal("0"):
                return None
            self._position_owner[signal.symbol] = strategy_name
            return OrderEvent(
                symbol=signal.symbol,
                timestamp=signal.timestamp,
                order_type=OrderType.MARKET,
                side=OrderSide.SELL,
                quantity=quantity,
                price=None,
            )

        elif signal.signal_type == SignalType.EXIT:
            pos = self._portfolio.positions.get(signal.symbol)
            if pos is None or pos.quantity <= Decimal("0"):
                return None
            close_side = (
                OrderSide.SELL if pos.side == OrderSide.BUY else OrderSide.BUY
            )
            return OrderEvent(
                symbol=signal.symbol,
                timestamp=signal.timestamp,
                order_type=OrderType.MARKET,
                side=close_side,
                quantity=pos.quantity,
                price=None,
            )

        return None

    def _calculate_weighted_quantity(
        self, bar: MarketEvent, weight: Decimal,
    ) -> Decimal:
        """Calculate position size adjusted by strategy weight."""
        equity_log = self._portfolio.equity_log
        if equity_log:
            equity = equity_log[-1]["equity"]
        else:
            equity = self._portfolio.cash

        if bar.close <= Decimal("0"):
            return Decimal("0")

        # Weight-adjusted: weight * 10% of equity / price
        quantity = (weight * equity * Decimal("0.10")) / bar.close
        return Decimal(str(int(quantity)))

    @staticmethod
    def _compute_strategy_pnl(fills: list[FillEvent]) -> Decimal:
        """Compute net PnL from a list of fills."""
        pnl = Decimal("0")
        open_fill: Optional[FillEvent] = None

        for fill in fills:
            if open_fill is None:
                open_fill = fill
            else:
                if fill.side != open_fill.side:
                    if open_fill.side == OrderSide.BUY:
                        trade_pnl = (fill.fill_price - open_fill.fill_price) * open_fill.quantity
                    else:
                        trade_pnl = (open_fill.fill_price - fill.fill_price) * open_fill.quantity
                    trade_pnl -= (open_fill.commission + open_fill.slippage + open_fill.spread_cost)
                    trade_pnl -= (fill.commission + fill.slippage + fill.spread_cost)
                    pnl += trade_pnl
                    open_fill = None
                else:
                    open_fill = fill

        return pnl
