"""
kill_zone.py — ICT Kill Zone session classification.

Classifies UTC timestamps into ICT trading sessions (kill zones) by
converting to US Eastern time.  The ``zoneinfo`` module (Python 3.9+)
handles EDT/EST transitions automatically.

Requirement: ICT-03
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")


class SessionType(Enum):
    LONDON_OPEN = "LONDON_OPEN"     # 02:00-04:59 ET
    NY_OPEN = "NY_OPEN"             # 07:00-09:59 ET
    LONDON_CLOSE = "LONDON_CLOSE"   # 10:00-11:59 ET
    NY_CLOSE = "NY_CLOSE"           # 14:00-15:59 ET
    OFF_SESSION = "OFF_SESSION"


class KillZoneFilter:
    """Filter timestamps by ICT kill-zone sessions.

    Parameters
    ----------
    active_sessions : list[SessionType] | None
        Sessions considered valid kill zones.
        Default: ``[LONDON_OPEN, NY_OPEN, NY_CLOSE]``.
    """

    _DEFAULT_SESSIONS = [
        SessionType.LONDON_OPEN,
        SessionType.NY_OPEN,
        SessionType.NY_CLOSE,
    ]

    def __init__(
        self,
        active_sessions: Optional[list[SessionType]] = None,
    ) -> None:
        self._active_sessions = (
            list(active_sessions) if active_sessions is not None
            else list(self._DEFAULT_SESSIONS)
        )

    def classify_session(self, timestamp: datetime) -> SessionType:
        """Return the session type for *timestamp*.

        Timezone-naive timestamps are assumed UTC.
        """
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        et_time = timestamp.astimezone(_ET)
        hour = et_time.hour

        if 2 <= hour <= 4:
            return SessionType.LONDON_OPEN
        if 7 <= hour <= 9:
            return SessionType.NY_OPEN
        if 10 <= hour <= 11:
            return SessionType.LONDON_CLOSE
        if 14 <= hour <= 15:
            return SessionType.NY_CLOSE
        return SessionType.OFF_SESSION

    def is_kill_zone(self, timestamp: datetime) -> bool:
        """Return True if *timestamp* falls within an active kill zone."""
        return self.classify_session(timestamp) in self._active_sessions
