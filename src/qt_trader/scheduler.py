from __future__ import annotations

from datetime import datetime

from qt_trader.market import TradingCalendar


class SessionScheduler:
    def __init__(self, calendar: TradingCalendar) -> None:
        self.calendar = calendar

    def should_run_now(self, current_time: datetime | None = None) -> bool:
        return self.calendar.status(current_time).is_open

    def describe(self, current_time: datetime | None = None) -> str:
        status = self.calendar.status(current_time)
        return (
            f"phase={status.phase}, is_open={status.is_open}, "
            f"next_open={status.next_open.isoformat()}"
        )
