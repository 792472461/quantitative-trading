"""Trading strategies."""

from qt_trader.strategy.auto_rotation import AutoRotationStrategy
from qt_trader.strategy.moving_average import MovingAverageCrossStrategy

__all__ = ["AutoRotationStrategy", "MovingAverageCrossStrategy"]
