"""
gated_strategy.py — Regime-gated strategy decorator.

Wraps any BaseStrategy with a RegimeClassifier gate:
signals from the inner strategy are only forwarded when
the current regime is in the allowed set.

The inner strategy is ALWAYS called (even when gated) so that
its stateful components (Swing, OB, FVG) stay synchronised.

Requirement: REG-04
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from src.events import MarketEvent, SignalEvent
from src.strategy.base import BaseStrategy
from src.strategy.regime.classifier import (
    RegimeClassifier,
    RegimeType,
    MarketRegime,
)


class RegimeGatedStrategy(BaseStrategy):
    """Decorator that gates an inner strategy by market regime.

    Parameters
    ----------
    inner_strategy : BaseStrategy
        The strategy whose signals are gated.
    allowed_regimes : list[RegimeType]
        Signals are only forwarded in these regimes.
    atr_period : int
        ATR period for regime classifier.
    adx_period : int
        ADX period for regime classifier.
    regime_lookback : int
        Rolling ATR history length.
    """

    def __init__(
        self,
        inner_strategy: BaseStrategy,
        allowed_regimes: list[RegimeType],
        atr_period: int = 14,
        adx_period: int = 14,
        regime_lookback: int = 50,
    ) -> None:
        super().__init__(
            symbol=inner_strategy.symbol,
            timeframe=inner_strategy.timeframe,
            max_buffer_size=500,
        )
        self._inner = inner_strategy
        self._allowed_regimes = set(allowed_regimes)
        self._regime_clf = RegimeClassifier(
            atr_period=atr_period,
            adx_period=adx_period,
            regime_lookback=regime_lookback,
        )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def current_regime(self) -> Optional[MarketRegime]:
        return self._regime_clf.regime

    @property
    def inner_strategy(self) -> BaseStrategy:
        return self._inner

    # ------------------------------------------------------------------
    # Main pipeline
    # ------------------------------------------------------------------

    def calculate_signals(self, event: MarketEvent) -> Optional[SignalEvent]:
        """Gate inner strategy signals by market regime.

        Pipeline:
        1. Update own buffer (for regime classifier)
        2. Classify regime
        3. ALWAYS delegate to inner strategy (keeps stateful components in sync)
        4. Gate: suppress signal if regime not in allowed set
        """
        # Step 1: Own buffer for regime classifier
        self.update_buffer(event)

        # Step 2: Classify current regime
        self._regime_clf.update(event, self._bar_buffer)

        # Step 3: ALWAYS call inner strategy
        signal = self._inner.calculate_signals(event)

        # Step 4: Gate
        regime = self._regime_clf.regime
        if regime is None or regime.regime_type not in self._allowed_regimes:
            return None

        return signal


# ---------------------------------------------------------------------------
# Factory function for dashboard integration
# ---------------------------------------------------------------------------

def create_regime_gated_ict(
    symbol: str,
    timeframe: str = "1h",
    max_buffer_size: int = 500,
    params: Optional[dict] = None,
) -> RegimeGatedStrategy:
    """Create an ICTStrategy wrapped with RegimeGatedStrategy.

    Parameters are forwarded to ICTStrategy; regime-specific params
    are extracted from the ``params`` dict:
      - atr_period (also forwarded to ICT)
      - adx_period
      - regime_lookback
      - allowed_regimes (list of RegimeType value strings)
    """
    from src.strategy.smc.ict_strategy import ICTStrategy

    p = dict(params) if params else {}

    atr_period = p.get("atr_period", 14)
    adx_period = p.get("adx_period", 14)
    regime_lookback = p.get("regime_lookback", 50)

    # Parse allowed_regimes from string list
    raw_regimes = p.get("allowed_regimes", ["STRONG_TREND", "MODERATE_TREND"])
    allowed_regimes = [RegimeType(r) for r in raw_regimes]

    inner = ICTStrategy(
        symbol=symbol,
        timeframe=timeframe,
        max_buffer_size=max_buffer_size,
        params=p,
    )

    return RegimeGatedStrategy(
        inner_strategy=inner,
        allowed_regimes=allowed_regimes,
        atr_period=atr_period,
        adx_period=adx_period,
        regime_lookback=regime_lookback,
    )
