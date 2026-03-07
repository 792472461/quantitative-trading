from datetime import datetime
from pathlib import Path
import json

import pandas as pd

from qt_trader.alerts import AlertNotifier
from qt_trader.backtest import BacktestEngine
from qt_trader.broker.factory import create_broker
from qt_trader.config import load_config
from qt_trader.costs import ExecutionCostModel
from qt_trader.data.akshare_data import AKShareDataFeed
from qt_trader.data.factory import create_data_feed
from qt_trader.logging_utils import JsonLogger
from qt_trader.market import TradingCalendar
from qt_trader.models import Order, OrderSide, Position
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
            symbols=config.data.symbols or [config.data.symbol],
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
    config.logging.jsonl_path = tmp_path / "runtime.jsonl"
    bars = create_data_feed(config).load()
    storage = SQLiteStorage(config.storage.sqlite_path)
    logger = JsonLogger(config.logging.jsonl_path)
    alert_notifier = AlertNotifier(config.alert, output_path=tmp_path / "alerts.log")

    runtime = PaperTradingRuntime(
        strategy=MovingAverageCrossStrategy(
            symbols=config.data.symbols or [config.data.symbol],
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
        logger=logger,
        alert_notifier=alert_notifier,
        max_drawdown_alert_pct=config.alert.max_drawdown_pct,
        rejected_order_alert_threshold=config.alert.rejected_order_threshold,
    )

    result = runtime.run(bars)
    counts = storage.counts()

    assert result.snapshots
    assert counts["orders"] == len(result.executed_orders) + len(result.rejected_orders)
    assert counts["fills"] == len(result.executed_orders)
    assert counts["snapshots"] == len(result.snapshots)
    assert counts["events"] >= len(result.executed_orders)
    assert config.logging.jsonl_path.exists()
    first_log = json.loads(config.logging.jsonl_path.read_text(encoding="utf-8").splitlines()[0])
    assert first_log["event_type"] == "runtime_started"


def test_akshare_feed_normalizes_and_exports_csv(tmp_path: Path) -> None:
    export_path = tmp_path / "akshare_export.csv"
    feed = AKShareDataFeed(
        symbol="600519",
        symbols=["600519"],
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

    feed._fetch_frame = lambda symbol: fake_fetch_frame()  # type: ignore[method-assign]
    bars = feed.load()

    assert len(bars) == 2
    assert export_path.exists()


def test_akshare_feed_falls_back_to_cached_csv(tmp_path: Path) -> None:
    export_path = tmp_path / "cached.csv"
    pd.DataFrame(
        {
            "datetime": ["2024-01-02", "2024-01-03"],
            "open": [100.0, 101.0],
            "high": [102.0, 103.0],
            "low": [99.0, 100.5],
            "close": [101.5, 102.5],
            "volume": [10000, 12000],
        }
    ).to_csv(export_path, index=False)

    feed = AKShareDataFeed(symbol="600519", symbols=["600519"], output_csv_path=export_path)

    def broken_fetch_frame(symbol: str) -> pd.DataFrame:
        raise RuntimeError("network unavailable")

    feed._fetch_frame = broken_fetch_frame  # type: ignore[method-assign]
    bars = feed.load()

    assert len(bars) == 2
    assert bars[0].close == 101.5


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


def test_multi_symbol_backtest_runs() -> None:
    config = load_config(Path("config/multi_symbol.yaml"))
    bars = create_data_feed(config).load()

    engine = BacktestEngine(
        strategy=MovingAverageCrossStrategy(
            symbols=config.data.symbols or [config.data.symbol],
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
    assert len({order.symbol for order in result.executed_orders}) >= 1


def test_portfolio_risk_limits_total_exposure_and_positions() -> None:
    risk_manager = RiskManager(
        max_position_pct=0.6,
        max_drawdown_pct=0.2,
        max_total_exposure_pct=0.6,
        max_positions=1,
        max_symbol_quantity=100,
    )
    portfolio = Portfolio(initial_cash=100000)
    snapshot = portfolio.snapshot(datetime.fromisoformat("2026-03-07T10:00:00"), {})

    first_order = Order(
        symbol="600519.SH",
        side=OrderSide.BUY,
        quantity=50,
        timestamp=datetime.fromisoformat("2026-03-07T10:00:00"),
        price=100.0,
    )
    accepted, _ = risk_manager.validate_order(first_order, snapshot, 100.0, None)
    assert accepted is True

    constrained_snapshot = portfolio.snapshot(
        datetime.fromisoformat("2026-03-07T10:00:00"),
        {"600519.SH": 100.0},
    )
    constrained_snapshot.positions_value = 55000
    constrained_snapshot.positions["600519.SH"] = Position(symbol="600519.SH", quantity=50, average_cost=100.0)

    second_order = Order(
        symbol="000001.SZ",
        side=OrderSide.BUY,
        quantity=100,
        timestamp=datetime.fromisoformat("2026-03-07T10:01:00"),
        price=100.0,
    )
    accepted, reason = risk_manager.validate_order(second_order, constrained_snapshot, 100.0, None)
    assert accepted is False
    assert reason in {"total exposure limit exceeded", "max positions exceeded"}


def test_execution_cost_model_applies_slippage_and_taxes() -> None:
    model = ExecutionCostModel(
        commission_rate=0.0003,
        min_commission=5.0,
        stamp_duty_rate=0.001,
        slippage_bps=5.0,
    )

    buy_price = model.execution_price(100.0, OrderSide.BUY)
    sell_price = model.execution_price(100.0, OrderSide.SELL)

    assert round(buy_price, 4) == 100.05
    assert round(sell_price, 4) == 99.95
    assert model.commission(buy_price, 10) == 5.0
    assert round(model.stamp_duty(sell_price, 100, OrderSide.SELL), 3) == 9.995
