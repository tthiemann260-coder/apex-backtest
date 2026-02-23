"""
engine.py — Backtest orchestrator for apex-backtest.

Wires all components (DataHandler, Strategy, Portfolio, ExecutionHandler)
into the event dispatch loop. The engine has NO trading logic of its own (EDA-03).

Each sweep iteration gets fresh components via create_engine() (EDA-04).

Event flow: MarketEvent → Strategy.calculate_signals() → OrderEvent →
ExecutionHandler.process_bar() → FillEvent → Portfolio.process_fill()
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from src.data_handler import DataHandler
from src.events import (
    MarketEvent, SignalEvent, OrderEvent, FillEvent,
    SignalType, OrderType, OrderSide,
)
from src.event_queue import EventQueue
from src.execution import ExecutionHandler
from src.portfolio import Portfolio
from src.strategy.base import BaseStrategy


@dataclass
class BacktestResult:
    """Container for backtest results."""
    equity_log: list[dict] = field(default_factory=list)
    fill_log: list[FillEvent] = field(default_factory=list)
    event_log: list = field(default_factory=list)
    final_equity: Decimal = Decimal("0")
    total_bars: int = 0


class BacktestEngine:
    """Event-driven backtest orchestrator.

    Dispatches events to the correct component without any trading logic.
    The engine only routes events — all decisions are made by Strategy,
    all execution by ExecutionHandler, all accounting by Portfolio.
    """

    def __init__(
        self,
        data_handler: DataHandler,
        strategy: BaseStrategy,
        portfolio: Portfolio,
        execution_handler: ExecutionHandler,
        risk_manager=None,
    ) -> None:
        self._data_handler = data_handler
        self._strategy = strategy
        self._portfolio = portfolio
        self._execution = execution_handler
        self._risk_manager = risk_manager
        self._event_queue = EventQueue()
        self._event_log: list = []

    def run(self) -> BacktestResult:
        """Run the backtest: consume all bars, process all events.

        Returns a BacktestResult with equity log, fill log, and event log.
        """
        total_bars = 0

        for bar in self._data_handler.stream_bars():
            total_bars += 1

            # 1. Process pending orders against this bar
            fills = self._execution.process_bar(bar)
            for fill in fills:
                self._event_log.append(fill)
                self._portfolio.process_fill(fill)

            # 2. Check margin after fills
            prices = {bar.symbol: bar.close}
            to_liquidate = self._portfolio.check_margin(prices)
            for symbol in to_liquidate:
                liq_fill = self._portfolio.force_liquidate(symbol, bar.close)
                if liq_fill:
                    self._event_log.append(liq_fill)

            # 3. Generate signals from strategy
            signal = self._strategy.calculate_signals(bar)
            if signal is not None:
                self._event_log.append(signal)
                order = self._signal_to_order(signal, bar)
                if order is not None:
                    self._event_log.append(order)
                    self._execution.submit_order(order)

            # 4. Update equity log
            self._portfolio.update_equity(bar)

        # Compute final equity
        final_equity = Decimal("0")
        if self._portfolio.equity_log:
            final_equity = self._portfolio.equity_log[-1]["equity"]

        return BacktestResult(
            equity_log=self._portfolio.equity_log,
            fill_log=self._portfolio.fill_log,
            event_log=self._event_log,
            final_equity=final_equity,
            total_bars=total_bars,
        )

    def _signal_to_order(
        self, signal: SignalEvent, bar: MarketEvent,
    ) -> Optional[OrderEvent]:
        """Convert a SignalEvent to an OrderEvent.

        LONG → BUY MARKET
        SHORT → SELL MARKET
        EXIT → close current position
        """
        # Risk gate — applies to LONG and SHORT, not EXIT
        if self._risk_manager is not None and signal.signal_type != SignalType.EXIT:
            can, reason = self._risk_manager.can_trade(self._portfolio, bar)
            if not can:
                return None

        if signal.signal_type == SignalType.LONG:
            # Validate order
            quantity = self._calculate_order_quantity(bar)
            if quantity <= Decimal("0"):
                return None
            valid, _ = self._portfolio.validate_order(
                bar.symbol, OrderSide.BUY, quantity, bar.close, bar.volume,
            )
            if not valid:
                return None
            return OrderEvent(
                symbol=signal.symbol,
                timestamp=signal.timestamp,
                order_type=OrderType.MARKET,
                side=OrderSide.BUY,
                quantity=quantity,
                price=None,
            )

        elif signal.signal_type == SignalType.SHORT:
            quantity = self._calculate_order_quantity(bar)
            if quantity <= Decimal("0"):
                return None
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

    def _calculate_order_quantity(self, bar: MarketEvent) -> Decimal:
        """Calculate order quantity based on risk settings."""
        if self._risk_manager is not None:
            return self._risk_manager.compute_quantity(
                self._portfolio, self._strategy, bar,
            )

        # Legacy fallback: 10% fixed fractional
        equity_log = self._portfolio.equity_log
        if equity_log:
            equity = equity_log[-1]["equity"]
        else:
            equity = self._portfolio.cash

        if bar.close <= Decimal("0"):
            return Decimal("0")
        quantity = (equity * Decimal("0.10")) / bar.close
        return Decimal(str(int(quantity)))


def create_engine(
    data_handler: DataHandler,
    strategy: BaseStrategy,
    initial_cash: Decimal = Decimal("10000"),
    slippage_pct: Decimal = Decimal("0.0001"),
    commission_per_trade: Decimal = Decimal("1.00"),
    commission_per_share: Decimal = Decimal("0.005"),
    spread_pct: Decimal = Decimal("0.0002"),
    margin_requirement: Decimal = Decimal("0.25"),
    risk_manager=None,
    trade_builder=None,
) -> BacktestEngine:
    """Factory function for creating fresh engine instances (EDA-04).

    Each call creates new Portfolio and ExecutionHandler instances
    to prevent state leakage between sweep iterations.

    Parameters
    ----------
    trade_builder : TradeBuilder, optional
        If provided, attached to Portfolio for automatic trade journaling.
    """
    portfolio = Portfolio(
        initial_cash=initial_cash,
        margin_requirement=margin_requirement,
    )
    if trade_builder is not None:
        portfolio.trade_builder = trade_builder
    execution = ExecutionHandler(
        slippage_pct=slippage_pct,
        commission_per_trade=commission_per_trade,
        commission_per_share=commission_per_share,
        spread_pct=spread_pct,
    )
    return BacktestEngine(
        data_handler=data_handler,
        strategy=strategy,
        portfolio=portfolio,
        execution_handler=execution,
        risk_manager=risk_manager,
    )
