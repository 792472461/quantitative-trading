from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from qt_trader.config import MarketConfig


@dataclass(slots=True)
class MarketStatus:
    is_trading_day: bool
    is_open: bool
    phase: str
    current_time: datetime
    next_open: datetime


class TradingCalendar:
    def __init__(self, config: MarketConfig) -> None:
        self.config = config
        self.timezone = ZoneInfo(config.timezone)
        self.holidays = {date.fromisoformat(item) for item in config.holidays}
        self.morning_start = self._parse_time(config.morning_start)
        self.morning_end = self._parse_time(config.morning_end)
        self.afternoon_start = self._parse_time(config.afternoon_start)
        self.afternoon_end = self._parse_time(config.afternoon_end)

    def status(self, current_time: datetime | None = None) -> MarketStatus:
        now = self._normalize_datetime(current_time)
        trading_day = self.is_trading_day(now.date())

        if not trading_day:
            return MarketStatus(
                is_trading_day=False,
                is_open=False,
                phase="closed",
                current_time=now,
                next_open=self.next_open_after(now),
            )

        current_clock = now.timetz().replace(tzinfo=None)
        if self.morning_start <= current_clock < self.morning_end:
            phase = "morning"
            is_open = True
        elif self.afternoon_start <= current_clock < self.afternoon_end:
            phase = "afternoon"
            is_open = True
        elif current_clock < self.morning_start:
            phase = "pre_open"
            is_open = False
        elif self.morning_end <= current_clock < self.afternoon_start:
            phase = "midday_break"
            is_open = False
        else:
            phase = "post_close"
            is_open = False

        return MarketStatus(
            is_trading_day=True,
            is_open=is_open,
            phase=phase,
            current_time=now,
            next_open=self.next_open_after(now),
        )

    def is_trading_day(self, current_date: date) -> bool:
        return current_date.weekday() in self.config.weekdays and current_date not in self.holidays

    def next_open_after(self, current_time: datetime) -> datetime:
        now = self._normalize_datetime(current_time)
        current_clock = now.timetz().replace(tzinfo=None)
        if self.is_trading_day(now.date()) and current_clock < self.morning_start:
            return self._combine(now.date(), self.morning_start)
        if self.is_trading_day(now.date()) and self.morning_end <= current_clock < self.afternoon_start:
            return self._combine(now.date(), self.afternoon_start)

        candidate = now.date()
        while True:
            candidate += timedelta(days=1)
            if self.is_trading_day(candidate):
                return self._combine(candidate, self.morning_start)

    def _combine(self, current_date: date, current_time: time) -> datetime:
        return datetime.combine(current_date, current_time, tzinfo=self.timezone)

    def _normalize_datetime(self, current_time: datetime | None) -> datetime:
        if current_time is None:
            return datetime.now(self.timezone)
        if current_time.tzinfo is None:
            return current_time.replace(tzinfo=self.timezone)
        return current_time.astimezone(self.timezone)

    @staticmethod
    def _parse_time(value: str) -> time:
        hour, minute = value.split(":")
        return time(hour=int(hour), minute=int(minute))
