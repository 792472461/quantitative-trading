from __future__ import annotations

from datetime import datetime

from qt_trader.alerts import AlertNotifier
from qt_trader.guardian import RuntimeStateStore
from qt_trader.logging_utils import JsonLogger
from qt_trader.risk import RiskManager
from qt_trader.storage import SQLiteStorage
from qt_trader.strategy.auto_rotation import AutoRotationStrategy
from qt_trader.strategy.moving_average import MovingAverageCrossStrategy


def build_strategy(config):
    symbols = config.data.symbols or [config.data.symbol]
    benchmark_symbol = config.strategy.benchmark_symbol
    trade_symbols = [symbol for symbol in symbols if symbol != benchmark_symbol]
    if config.strategy.name == "moving_average_cross":
        return MovingAverageCrossStrategy(
            symbols=trade_symbols,
            fast_window=config.strategy.fast_window,
            slow_window=config.strategy.slow_window,
            trade_size=config.strategy.trade_size,
            market_filter_enabled=config.strategy.market_filter_enabled,
            benchmark_symbol=benchmark_symbol,
            market_fast_window=config.strategy.market_fast_window,
            market_slow_window=config.strategy.market_slow_window,
        )
    if config.strategy.name == "auto_rotation":
        return AutoRotationStrategy(
            symbols=trade_symbols,
            trade_size=config.strategy.trade_size,
            selection_window=config.strategy.selection_window,
            selection_top_n=config.strategy.selection_top_n,
            selection_volume_window=config.strategy.selection_volume_window,
            selection_exit_rank_buffer=config.strategy.selection_exit_rank_buffer,
            min_holding_days=config.strategy.min_holding_days,
        )
    raise ValueError(f"Unsupported strategy: {config.strategy.name}")


def build_runtime_dependencies(app_config):
    storage = SQLiteStorage(app_config.storage.sqlite_path)
    logger = JsonLogger(app_config.logging.jsonl_path)
    alert_notifier = AlertNotifier(app_config.alert)
    state_store = RuntimeStateStore(app_config.runtime.state_path)
    return storage, logger, alert_notifier, state_store


def build_risk_manager(app_config):
    return RiskManager(
        max_position_pct=app_config.backtest.max_position_pct,
        max_drawdown_pct=app_config.backtest.max_drawdown_pct,
        max_total_exposure_pct=app_config.backtest.max_total_exposure_pct,
        max_positions=app_config.backtest.max_positions,
        max_symbol_quantity=app_config.backtest.max_symbol_quantity,
        t_plus_one_sell=app_config.backtest.t_plus_one_sell,
    )


def persist_backtest_run(storage: SQLiteStorage, app_config, metrics, final_equity: float) -> None:
    symbols = app_config.data.symbols or [app_config.data.symbol]
    storage.save_backtest_run(
        created_at=datetime.now().isoformat(),
        strategy_name=app_config.strategy.name,
        symbols=symbols,
        fast_window=app_config.strategy.fast_window,
        slow_window=app_config.strategy.slow_window,
        trade_size=app_config.strategy.trade_size,
        metrics=metrics,
        final_equity=final_equity,
    )


def parse_int_list(raw: str) -> list[int]:
    values = [int(part.strip()) for part in raw.split(",") if part.strip()]
    if not values:
        raise ValueError("at least one integer value is required")
    return values
