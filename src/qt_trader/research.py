from __future__ import annotations

from dataclasses import dataclass

from qt_trader.analytics import BacktestMetrics, analyze_backtest
from qt_trader.backtest import BacktestEngine
from qt_trader.config import AppConfig
from qt_trader.costs import ExecutionCostModel
from qt_trader.models import Bar
from qt_trader.portfolio import Portfolio
from qt_trader.risk import RiskManager
from qt_trader.strategy.moving_average import MovingAverageCrossStrategy
from qt_trader.broker.paper import PaperBroker


@dataclass(slots=True)
class ParameterSweepResult:
    fast_window: int
    slow_window: int
    trade_size: int
    metrics: BacktestMetrics


def optimize_moving_average_parameters(
    bars: list[Bar],
    config: AppConfig,
    fast_windows: list[int],
    slow_windows: list[int],
    trade_size: int | None = None,
) -> list[ParameterSweepResult]:
    results: list[ParameterSweepResult] = []
    symbols = config.data.symbols or [config.data.symbol]
    resolved_trade_size = trade_size or config.strategy.trade_size

    for fast_window in sorted(set(fast_windows)):
        for slow_window in sorted(set(slow_windows)):
            if fast_window >= slow_window:
                continue
            portfolio = Portfolio(initial_cash=config.backtest.initial_cash)
            broker = PaperBroker(
                cost_model=ExecutionCostModel(
                    commission_rate=config.backtest.commission_rate,
                    min_commission=config.backtest.min_commission,
                    stamp_duty_rate=config.backtest.stamp_duty_rate,
                    slippage_bps=config.backtest.slippage_bps,
                ),
                portfolio=portfolio,
            )
            engine = BacktestEngine(
                strategy=MovingAverageCrossStrategy(
                    symbols=symbols,
                    fast_window=fast_window,
                    slow_window=slow_window,
                    trade_size=resolved_trade_size,
                ),
                broker=broker,
                portfolio=portfolio,
                risk_manager=RiskManager(
                    max_position_pct=config.backtest.max_position_pct,
                    max_drawdown_pct=config.backtest.max_drawdown_pct,
                    max_total_exposure_pct=config.backtest.max_total_exposure_pct,
                    max_positions=config.backtest.max_positions,
                    max_symbol_quantity=config.backtest.max_symbol_quantity,
                ),
            )
            result = engine.run(bars)
            metrics = analyze_backtest(result, config.backtest.initial_cash)
            results.append(
                ParameterSweepResult(
                    fast_window=fast_window,
                    slow_window=slow_window,
                    trade_size=resolved_trade_size,
                    metrics=metrics,
                )
            )

    results.sort(
        key=lambda item: (
            item.metrics.total_return_pct,
            item.metrics.sharpe_ratio,
            -item.metrics.max_drawdown_pct,
            item.metrics.profit_factor,
        ),
        reverse=True,
    )
    return results
