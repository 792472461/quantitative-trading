from datetime import datetime
from pathlib import Path

import pandas as pd

from qt_trader.backtest import BacktestEngine
from qt_trader.broker.factory import create_broker
from qt_trader.config import load_config
from qt_trader.data.akshare_data import AKShareDataFeed
from qt_trader.data.factory import create_data_feed
from qt_trader.market import TradingCalendar
from qt_trader.portfolio import Portfolio
from qt_trader.risk import RiskManager
from qt_trader.runtime import PaperTradingRuntime
from qt_trader.scheduler import SessionScheduler
from qt_trader.storage import SQLiteStorage
from qt_trader.strategy.moving_average import MovingAverageCrossStrategy


def test_backtest_runs_end_to_end() -> None:
    config = load_config(Path("config/example.yaml"))
    bars = create_data_feed(config).load()

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
    bars = create_data_feed(config).load()
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


def test_akshare_feed_normalizes_and_exports_csv(tmp_path: Path) -> None:
    export_path = tmp_path / "akshare_export.csv"
    feed = AKShareDataFeed(
        symbol="600519",
        period="daily",
        start_date="20240101",
        end_date="20240131",
        adjust="qfq",
        output_csv_path=export_path,
    )

    def fake_fetch_frame() -> pd.DataFrame:
        return pd.DataFrame(
            {
                "日期": ["2024-01-02", "2024-01-03"],
                "开盘": [100.0, 101.0],
                "最高": [102.0, 103.0],
                "最低": [99.0, 100.5],
                "收盘": [101.5, 102.5],
                "成交量": [10000, 12000],
            }
        )

    feed._fetch_frame = fake_fetch_frame  # type: ignore[method-assign]
    bars = feed.load()

    assert len(bars) == 2
    assert export_path.exists()


def test_trading_calendar_and_scheduler() -> None:
    config = load_config(Path("config/example.yaml"))
    calendar = TradingCalendar(config.market)
    scheduler = SessionScheduler(calendar)

    open_time = datetime.fromisoformat("2026-03-06T10:00:00")
    lunch_time = datetime.fromisoformat("2026-03-06T12:00:00")
    weekend_time = datetime.fromisoformat("2026-03-07T10:00:00")

    assert calendar.status(open_time).is_open is True
    assert calendar.status(lunch_time).phase == "midday_break"
    assert calendar.status(weekend_time).is_trading_day is False
    assert scheduler.should_run_now(open_time) is True
    assert scheduler.should_run_now(weekend_time) is False
