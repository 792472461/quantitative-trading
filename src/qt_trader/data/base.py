from __future__ import annotations

from abc import ABC, abstractmethod

from qt_trader.models import Bar


class MarketDataFeed(ABC):
    @abstractmethod
    def load(self) -> list[Bar]:
        raise NotImplementedError
