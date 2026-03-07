from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(str, Enum):
    NEW = "NEW"
    REJECTED = "REJECTED"
    FILLED = "FILLED"


@dataclass(slots=True)
class Bar:
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(slots=True)
class Signal:
    symbol: str
    side: OrderSide
    quantity: int
    reason: str = ""


@dataclass(slots=True)
class Order:
    symbol: str
    side: OrderSide
    quantity: int
    timestamp: datetime
    price: float | None = None
    status: OrderStatus = OrderStatus.NEW
    reason: str = ""


@dataclass(slots=True)
class Fill:
    symbol: str
    side: OrderSide
    quantity: int
    price: float
    timestamp: datetime
    commission: float = 0.0
    stamp_duty: float = 0.0
    slippage_cost: float = 0.0

    @property
    def total_fees(self) -> float:
        return self.commission + self.stamp_duty


@dataclass(slots=True)
class Position:
    symbol: str
    quantity: int = 0
    average_cost: float = 0.0


@dataclass(slots=True)
class PortfolioSnapshot:
    timestamp: datetime
    cash: float
    total_value: float
    positions_value: float
    drawdown: float
    positions: dict[str, Position] = field(default_factory=dict)


@dataclass(slots=True)
class RuntimeEvent:
    event_type: str
    timestamp: datetime
    severity: str
    message: str
