"""
inducement.py — ICT Inducement (IDM) detection for SMC.

Identifies inducement points — minor swing levels that act as retail traps
between a Break of Structure (BOS) and the expected continuation move.

After a bullish BOS, the lowest minor swing low between the BOS bar and
the current bar is the inducement.  When price sweeps through it, the IDM
is "cleared", increasing entry conviction for the ICT strategy.

Mirror logic applies for bearish BOS (highest minor swing high = IDM).

The detector uses a secondary SwingDetector (strength=1) internally to
find minor swings, while the primary detector (strength=2+) provides the
structural swings.

Requirement: ICT-02
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from src.events import MarketEvent
from src.strategy.smc.structure import StructureBreak
from src.strategy.smc.swing_detector import SwingDetector, SwingPoint


@dataclass(frozen=True)
class InducementPoint:
    """Immutable record of an inducement (IDM) level."""
    direction: str                    # "bullish" or "bearish" (trap direction)
    idm_level: Decimal                # The IDM swing price
    idm_bar_idx: int
    cleared: bool                     # True once price swept through the IDM
    cleared_bar_idx: Optional[int]    # Bar index where IDM was cleared


class InducementDetector:
    """Detects and tracks inducement (IDM) points after BOS events.

    Parameters
    ----------
    secondary_strength : int
        Fractal strength for the internal minor-swing detector. Must be
        lower than the primary detector's strength to capture smaller
        retracements. Default: 1.
    max_idm : int
        Maximum number of inducement records to retain. Default: 10.
    """

    def __init__(
        self,
        secondary_strength: int = 1,
        max_idm: int = 10,
    ) -> None:
        self._secondary_detector = SwingDetector(
            strength=secondary_strength,
            max_history=50,
        )
        self._max_idm = max_idm
        self._active_idm: list[InducementPoint] = []
        self._last_bos_bar: int = -1

    # ------------------------------------------------------------------
    # Public API — secondary swing feeding
    # ------------------------------------------------------------------

    def feed_bar(
        self,
        bar_buffer: list[MarketEvent],
        bar_count: int,
    ) -> None:
        """Feed a bar to the internal secondary SwingDetector.

        Must be called each bar so the minor-swing detector stays in sync.

        Parameters
        ----------
        bar_buffer : list[MarketEvent]
            Same rolling buffer passed to the primary SwingDetector.
        bar_count : int
            Current absolute bar index (1-based count of bars seen).
        """
        self._secondary_detector.detect_confirmed_swings(bar_buffer, bar_count)

    # ------------------------------------------------------------------
    # Public API — IDM detection
    # ------------------------------------------------------------------

    def detect_inducement(
        self,
        primary_highs: list[SwingPoint],
        primary_lows: list[SwingPoint],
        last_bos: Optional[StructureBreak],
        bar_idx: int,
    ) -> Optional[InducementPoint]:
        """Scan for a new inducement point after a BOS.

        Only triggers once per BOS (tracked via ``_last_bos_bar``).

        Parameters
        ----------
        primary_highs : list[SwingPoint]
            Swing highs from the primary (higher-strength) detector.
        primary_lows : list[SwingPoint]
            Swing lows from the primary detector.
        last_bos : Optional[StructureBreak]
            The most recent BOS/CHOCH event, or None.
        bar_idx : int
            Current absolute bar index.

        Returns
        -------
        Optional[InducementPoint]
            Newly detected IDM, or None.
        """
        if last_bos is None:
            return None
        if last_bos.bar_idx == self._last_bos_bar:
            return None  # Already processed this BOS

        self._last_bos_bar = last_bos.bar_idx
        idm: Optional[InducementPoint] = None

        if last_bos.direction == "bullish":
            # After bullish BOS: find lowest minor swing low between BOS and now
            idm = self._find_bullish_idm(last_bos.bar_idx, bar_idx)
        elif last_bos.direction == "bearish":
            # After bearish BOS: find highest minor swing high between BOS and now
            idm = self._find_bearish_idm(last_bos.bar_idx, bar_idx)

        if idm is not None:
            self._active_idm.append(idm)
            if len(self._active_idm) > self._max_idm:
                self._active_idm = self._active_idm[-self._max_idm:]

        return idm

    def check_idm_cleared(
        self,
        event: MarketEvent,
        bar_idx: int,
    ) -> Optional[InducementPoint]:
        """Check if the current bar clears any active (uncleared) IDM.

        Parameters
        ----------
        event : MarketEvent
            Current bar data.
        bar_idx : int
            Current absolute bar index.

        Returns
        -------
        Optional[InducementPoint]
            The newly cleared IDM (with ``cleared=True``), or None.
        """
        for i, idm in enumerate(self._active_idm):
            if idm.cleared:
                continue

            cleared = False
            if idm.direction == "bullish" and event.low < idm.idm_level:
                cleared = True
            elif idm.direction == "bearish" and event.high > idm.idm_level:
                cleared = True

            if cleared:
                updated = InducementPoint(
                    direction=idm.direction,
                    idm_level=idm.idm_level,
                    idm_bar_idx=idm.idm_bar_idx,
                    cleared=True,
                    cleared_bar_idx=bar_idx,
                )
                self._active_idm[i] = updated
                return updated

        return None

    def has_cleared_idm(self, direction: str) -> bool:
        """Return True if any IDM in the given direction has been cleared.

        Parameters
        ----------
        direction : str
            ``"bullish"`` or ``"bearish"``.
        """
        return any(
            idm.cleared and idm.direction == direction
            for idm in self._active_idm
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _find_bullish_idm(
        self,
        bos_bar: int,
        current_bar: int,
    ) -> Optional[InducementPoint]:
        """Find the lowest minor swing low between bos_bar and current_bar."""
        candidates = [
            sl for sl in self._secondary_detector.swing_lows
            if bos_bar < sl.abs_idx < current_bar
        ]
        if not candidates:
            return None

        lowest = min(candidates, key=lambda s: s.price)
        return InducementPoint(
            direction="bullish",
            idm_level=lowest.price,
            idm_bar_idx=lowest.abs_idx,
            cleared=False,
            cleared_bar_idx=None,
        )

    def _find_bearish_idm(
        self,
        bos_bar: int,
        current_bar: int,
    ) -> Optional[InducementPoint]:
        """Find the highest minor swing high between bos_bar and current_bar."""
        candidates = [
            sh for sh in self._secondary_detector.swing_highs
            if bos_bar < sh.abs_idx < current_bar
        ]
        if not candidates:
            return None

        highest = max(candidates, key=lambda s: s.price)
        return InducementPoint(
            direction="bearish",
            idm_level=highest.price,
            idm_bar_idx=highest.abs_idx,
            cleared=False,
            cleared_bar_idx=None,
        )
