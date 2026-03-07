from pathlib import Path

from qt_trader.backtest import BacktestEngine
from qt_trader.broker.factory import create_broker
from qt_trader.config import load_config
from qt_trader.data.csv_data import CSVBarFeed
from qt_trader.portfolio import Portfolio
from qt_trader.risk import RiskManager
from qt_trader.runtime import PaperTradingRuntime
from qt_trader.storage import SQLiteStorage
from qt_trader.strategy.moving_average import MovingAverageCrossStrategy


def test_backtest_runs_end_to_end() -> None:
    config = load_config(Path("config/example.yaml"))
    bars = CSVBarFeed(
        csv_path=config.data.csv_path,
        symbol=config.data.symbol,
        datetime_column=config.data.datetime_column,
    ).load()

    engine = BacktestEngine(
        strategy=MovingAverageCrossStrategy(
            symbol=config.data.symbol,
            fast_window=config.strategy.fast_window,
            slow_window=config.strategy.slow_window,
            trade_size=config.strategy.trade_size,
        ),
        broker=create_broker(config),
        portfolio=Portfolio(initial_cash=config.backtest.initial_cash),
        risk_manager=RiskManager(
            max_position_pct=config.backtest.max_position_pct,
            max_drawdown_pct=config.backtest.max_drawdown_pct,
        ),
    )

    result = engine.run(bars)

    assert result.final_snapshot is not None
    assert result.final_snapshot.total_value > 0


def test_paper_trading_persists_state(tmp_path: Path) -> None:
    config = load_config(Path("config/example.yaml"))
    config.storage.sqlite_path = tmp_path / "runtime.db"
    bars = CSVBarFeed(
        csv_path=config.data.csv_path,
        symbol=config.data.symbol,
        datetime_column=config.data.datetime_column,
    ).load()
    storage = SQLiteStorage(config.storage.sqlite_path)

    runtime = PaperTradingRuntime(
        strategy=MovingAverageCrossStrategy(
            symbol=config.data.symbol,
            fast_window=config.strategy.fast_window,
            slow_window=config.strategy.slow_window,
            trade_size=config.strategy.trade_size,
        ),
        broker=create_broker(config),
        portfolio=Portfolio(initial_cash=config.backtest.initial_cash),
        risk_manager=RiskManager(
            max_position_pct=config.backtest.max_position_pct,
            max_drawdown_pct=config.backtest.max_drawdown_pct,
        ),
        storage=storage,
        persist_snapshots=True,
        sleep_seconds=0.0,
    )

    result = runtime.run(bars)
    counts = storage.counts()

    assert result.snapshots
    assert counts["orders"] == len(result.executed_orders) + len(result.rejected_orders)
    assert counts["fills"] == len(result.executed_orders)
    assert counts["snapshots"] == len(result.snapshots)
