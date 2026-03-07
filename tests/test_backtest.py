from datetime import datetime
from pathlib import Path
import json
import os

import pandas as pd

from qt_trader.alerts import AlertNotifier
from qt_trader.backtest import BacktestEngine
from qt_trader.broker.factory import create_broker
from qt_trader.config import load_config
from qt_trader.costs import ExecutionCostModel
from qt_trader.data.akshare_data import AKShareDataFeed
from qt_trader.data.factory import create_data_feed
from qt_trader.guardian import RuntimeLock, RuntimeLockError, RuntimeStateStore
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
    portfolio = Portfolio(initial_cash=config.backtest.initial_cash)

    engine = BacktestEngine(
        strategy=MovingAverageCrossStrategy(
            symbols=config.data.symbols or [config.data.symbol],
            fast_window=config.strategy.fast_window,
            slow_window=config.strategy.slow_window,
            trade_size=config.strategy.trade_size,
        ),
        broker=create_broker(config, portfolio=portfolio),
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

    assert result.final_snapshot is not None
    assert result.final_snapshot.total_value > 0


def test_paper_trading_persists_state(tmp_path: Path) -> None:
    config = load_config(Path("config/example.yaml"))
    config.storage.sqlite_path = tmp_path / "runtime.db"
    config.logging.jsonl_path = tmp_path / "runtime.jsonl"
    config.runtime.state_path = tmp_path / "runtime_state.json"
    bars = create_data_feed(config).load()
    storage = SQLiteStorage(config.storage.sqlite_path)
    logger = JsonLogger(config.logging.jsonl_path)
    alert_notifier = AlertNotifier(config.alert, output_path=tmp_path / "alerts.log")
    state_store = RuntimeStateStore(config.runtime.state_path)
    portfolio = Portfolio(initial_cash=config.backtest.initial_cash)

    runtime = PaperTradingRuntime(
        strategy=MovingAverageCrossStrategy(
            symbols=config.data.symbols or [config.data.symbol],
            fast_window=config.strategy.fast_window,
            slow_window=config.strategy.slow_window,
            trade_size=config.strategy.trade_size,
        ),
        broker=create_broker(config, portfolio=portfolio),
        portfolio=portfolio,
        risk_manager=RiskManager(
            max_position_pct=config.backtest.max_position_pct,
            max_drawdown_pct=config.backtest.max_drawdown_pct,
            max_total_exposure_pct=config.backtest.max_total_exposure_pct,
            max_positions=config.backtest.max_positions,
            max_symbol_quantity=config.backtest.max_symbol_quantity,
        ),
        storage=storage,
        persist_snapshots=True,
        sleep_seconds=0.0,
        logger=logger,
        alert_notifier=alert_notifier,
        max_drawdown_alert_pct=config.alert.max_drawdown_pct,
        rejected_order_alert_threshold=config.alert.rejected_order_threshold,
        state_store=state_store,
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
    assert state_store.load().last_status == "completed"


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
    holiday_time = datetime.fromisoformat("2026-10-01T10:00:00")
    makeup_workday_time = datetime.fromisoformat("2026-02-14T10:00:00")

    assert calendar.status(open_time).is_open is True
    assert calendar.status(lunch_time).phase == "midday_break"
    assert calendar.status(weekend_time).is_trading_day is False
    assert calendar.status(holiday_time).is_trading_day is False
    assert calendar.status(makeup_workday_time).is_trading_day is True
    assert scheduler.should_run_now(open_time) is True
    assert scheduler.should_run_now(weekend_time) is False
    assert scheduler.should_run_now(makeup_workday_time) is True


def test_multi_symbol_backtest_runs() -> None:
    config = load_config(Path("config/multi_symbol.yaml"))
    bars = create_data_feed(config).load()
    portfolio = Portfolio(initial_cash=config.backtest.initial_cash)

    engine = BacktestEngine(
        strategy=MovingAverageCrossStrategy(
            symbols=config.data.symbols or [config.data.symbol],
            fast_window=config.strategy.fast_window,
            slow_window=config.strategy.slow_window,
            trade_size=config.strategy.trade_size,
        ),
        broker=create_broker(config, portfolio=portfolio),
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


def test_runtime_lock_and_state_store(tmp_path: Path) -> None:
    lock_path = tmp_path / "runtime.lock"
    state_path = tmp_path / "runtime_state.json"
    state_store = RuntimeStateStore(state_path)

    with RuntimeLock(lock_path):
        assert lock_path.exists()
        state_store.mark_started()
        assert state_store.load().last_status == "running"
        try:
            with RuntimeLock(lock_path):
                raise AssertionError("nested lock should not succeed")
        except RuntimeLockError:
            pass
        else:
            raise AssertionError("RuntimeLockError was not raised")

    assert not lock_path.exists()
    state_store.mark_failed("boom", 1)
    assert state_store.load().last_status == "failed"
    state_store.mark_completed()
    assert state_store.load().last_status == "completed"


def test_storage_dashboard_queries(tmp_path: Path) -> None:
    storage = SQLiteStorage(tmp_path / "dashboard.db")
    config = load_config(Path("config/example.yaml"))
    config.storage.sqlite_path = tmp_path / "dashboard.db"
    config.logging.jsonl_path = tmp_path / "runtime.jsonl"
    config.runtime.state_path = tmp_path / "runtime_state.json"
    bars = create_data_feed(config).load()
    portfolio = Portfolio(initial_cash=config.backtest.initial_cash)

    runtime = PaperTradingRuntime(
        strategy=MovingAverageCrossStrategy(
            symbols=config.data.symbols or [config.data.symbol],
            fast_window=config.strategy.fast_window,
            slow_window=config.strategy.slow_window,
            trade_size=config.strategy.trade_size,
        ),
        broker=create_broker(config, portfolio=portfolio),
        portfolio=portfolio,
        risk_manager=RiskManager(
            max_position_pct=config.backtest.max_position_pct,
            max_drawdown_pct=config.backtest.max_drawdown_pct,
            max_total_exposure_pct=config.backtest.max_total_exposure_pct,
            max_positions=config.backtest.max_positions,
            max_symbol_quantity=config.backtest.max_symbol_quantity,
        ),
        storage=storage,
        state_store=RuntimeStateStore(config.runtime.state_path),
    )
    runtime.run(bars)

    summary = storage.dashboard_summary()
    recent_events = storage.recent_events(limit=3)
    symbol_summary = storage.symbol_fill_summary()

    assert summary.orders >= 0
    assert summary.events > 0
    assert len(recent_events) <= 3
    assert isinstance(symbol_summary, list)


def test_paper_broker_account_queries() -> None:
    config = load_config(Path("config/example.yaml"))
    portfolio = Portfolio(initial_cash=config.backtest.initial_cash)
    broker = create_broker(config, portfolio=portfolio)

    account = broker.get_account_info()
    positions = broker.get_positions()
    orders = broker.get_orders()

    assert account.broker == "paper"
    assert account.cash == config.backtest.initial_cash
    assert positions == []
    assert orders == []


def test_readonly_broker_account_queries() -> None:
    config = load_config(Path("config/readonly_broker.yaml"))
    os.environ[config.broker.api_key_env] = "demo-key"
    os.environ[config.broker.api_secret_env] = "demo-secret"
    os.environ[config.broker.account_id_env] = "readonly-demo-001"

    broker = create_broker(config)
    account = broker.get_account_info()
    positions = broker.get_positions()
    orders = broker.get_orders()

    assert account.environment == "readonly"
    assert account.account_id == "readonly-demo-001"
    assert len(positions) == 2
    assert len(orders) == 2
