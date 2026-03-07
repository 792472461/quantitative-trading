from datetime import datetime
from pathlib import Path
import json
import os

import pandas as pd

from qt_trader.alerts import AlertNotifier
from qt_trader.analytics import analyze_backtest
from qt_trader.backtest import BacktestEngine
from qt_trader.broker.guojin import GuojinHTTPReadOnlyBroker
from qt_trader.broker.http_readonly import HTTPReadOnlyBroker
from qt_trader.broker.factory import create_broker
from qt_trader.config import load_config
from qt_trader.costs import ExecutionCostModel
from qt_trader.data.akshare_data import AKShareDataFeed
from qt_trader.data.factory import create_data_feed
from qt_trader.guardian import RuntimeLock, RuntimeLockError, RuntimeStateStore
from qt_trader.logging_utils import JsonLogger
from qt_trader.market import TradingCalendar
from qt_trader.models import AccountInfo, Order, OrderInfo, OrderSide, Position, PositionInfo
from qt_trader.portfolio import Portfolio
from qt_trader.readiness import run_preflight_checks
from qt_trader.research import optimize_moving_average_parameters
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
    metrics = analyze_backtest(result, config.backtest.initial_cash)

    assert result.final_snapshot is not None
    assert result.final_snapshot.total_value > 0
    assert metrics.trade_count >= 0
    assert metrics.max_drawdown_pct >= 0


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
    assert summary.backtest_runs == 0
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


def test_broker_snapshot_sync_to_storage(tmp_path: Path) -> None:
    config = load_config(Path("config/readonly_broker.yaml"))
    config.storage.sqlite_path = tmp_path / "broker_sync.db"
    os.environ[config.broker.api_key_env] = "demo-key"
    os.environ[config.broker.api_secret_env] = "demo-secret"
    os.environ[config.broker.account_id_env] = "readonly-demo-001"

    storage = SQLiteStorage(config.storage.sqlite_path)
    broker = create_broker(config)
    account = broker.get_account_info()
    positions = broker.get_positions()
    orders = broker.get_orders()
    storage.save_broker_snapshot(account, positions, orders, "2026-03-07T12:00:00")

    counts = storage.counts()
    latest_account = storage.latest_broker_account()

    assert counts["broker_accounts"] == 1
    assert counts["broker_positions"] == 2
    assert counts["broker_orders"] == 2
    assert latest_account is not None
    assert latest_account["account_id"] == "readonly-demo-001"


def test_broker_sync_summary_detects_account_and_position_changes(tmp_path: Path) -> None:
    storage = SQLiteStorage(tmp_path / "broker_sync_summary.db")
    account = AccountInfo(
        account_id="readonly-demo-001",
        broker="readonly",
        cash=100000.0,
        total_equity=120000.0,
        buying_power=80000.0,
        environment="readonly",
    )
    previous_positions = [
        PositionInfo(
            symbol="600519.SH",
            quantity=10,
            average_cost=1500.0,
            market_price=1550.0,
            market_value=15500.0,
        )
    ]
    current_positions = [
        PositionInfo(
            symbol="600519.SH",
            quantity=15,
            average_cost=1500.0,
            market_price=1560.0,
            market_value=23400.0,
        ),
        PositionInfo(
            symbol="000001.SZ",
            quantity=20,
            average_cost=12.0,
            market_price=12.5,
            market_value=250.0,
        ),
    ]
    previous_orders = [
        OrderInfo(
            symbol="600519.SH",
            side="BUY",
            quantity=10,
            price=1500.0,
            status="FILLED",
            timestamp=datetime.fromisoformat("2026-03-07T09:35:00"),
            reason="previous_sync",
        )
    ]
    current_orders = [
        OrderInfo(
            symbol="600519.SH",
            side="BUY",
            quantity=10,
            price=1500.0,
            status="FILLED",
            timestamp=datetime.fromisoformat("2026-03-07T09:35:00"),
            reason="previous_sync",
        ),
        OrderInfo(
            symbol="000001.SZ",
            side="BUY",
            quantity=20,
            price=12.0,
            status="NEW",
            timestamp=datetime.fromisoformat("2026-03-07T10:05:00"),
            reason="latest_sync",
        ),
    ]

    storage.save_broker_snapshot(account, previous_positions, previous_orders, "2026-03-07T10:00:00")
    storage.save_broker_snapshot(
        AccountInfo(
            account_id="readonly-demo-001",
            broker="readonly",
            cash=98000.0,
            total_equity=123000.0,
            buying_power=76000.0,
            environment="readonly",
        ),
        current_positions,
        current_orders,
        "2026-03-07T11:00:00",
    )

    summary = storage.latest_broker_sync_summary()
    position_changes = storage.latest_broker_position_changes(limit=5)

    assert summary is not None
    assert summary.previous_synced_at == "2026-03-07T10:00:00"
    assert summary.cash_change == -2000.0
    assert summary.total_equity_change == 3000.0
    assert summary.position_added == 1
    assert summary.position_removed == 0
    assert summary.position_changed == 1
    assert summary.broker_order_count == 2
    assert summary.broker_order_change == 1
    assert len(position_changes) == 2
    assert position_changes[0].symbol == "600519.SH"
    assert position_changes[0].status == "UPDATED"
    assert position_changes[1].symbol == "000001.SZ"
    assert position_changes[1].status == "ADDED"


def test_http_readonly_broker_queries() -> None:
    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self):
            return self.payload

    class FakeSession:
        def get(self, url: str, *, headers: dict[str, str], timeout: float):
            if url.endswith("/account"):
                return FakeResponse(
                    {
                        "account": {
                            "account_id": "http-demo-001",
                            "cash": 100000,
                            "total_equity": 123456,
                            "buying_power": 99999,
                            "environment": "readonly",
                        }
                    }
                )
            if url.endswith("/positions"):
                return FakeResponse(
                    {
                        "positions": [
                            {
                                "symbol": "600519.SH",
                                "quantity": 10,
                                "average_cost": 1500.0,
                                "market_price": 1550.0,
                                "market_value": 15500.0,
                            }
                        ]
                    }
                )
            return FakeResponse(
                {
                    "orders": [
                        {
                            "symbol": "600519.SH",
                            "side": "BUY",
                            "quantity": 10,
                            "price": 1500.0,
                            "status": "FILLED",
                            "timestamp": "2026-03-07T09:35:00",
                            "reason": "api_sync_sample",
                        }
                    ]
                }
            )

    broker = HTTPReadOnlyBroker(
        broker_name="http_readonly",
        account_id="http-demo-001",
        base_url="https://broker.example.com/api/v1",
        account_endpoint="/account",
        positions_endpoint="/positions",
        orders_endpoint="/orders",
        api_key="demo-key",
        api_secret="demo-secret",
        session=FakeSession(),
    )

    account = broker.get_account_info()
    positions = broker.get_positions()
    orders = broker.get_orders()

    assert account.account_id == "http-demo-001"
    assert len(positions) == 1
    assert len(orders) == 1


def test_guojin_http_readonly_factory() -> None:
    config = load_config(Path("config/guojin_http_readonly.yaml"))
    os.environ[config.broker.api_key_env] = "demo-key"
    os.environ[config.broker.api_secret_env] = "demo-secret"
    os.environ[config.broker.account_id_env] = "guojin-demo-001"

    broker = create_broker(config)

    assert isinstance(broker, GuojinHTTPReadOnlyBroker)


def test_backtest_analytics_computes_trade_metrics() -> None:
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
    metrics = analyze_backtest(result, config.backtest.initial_cash)

    assert metrics.trade_count == len(result.fills) // 2
    assert metrics.total_return_pct != 0
    assert metrics.sharpe_ratio != 0
    assert metrics.expectancy != 0


def test_parameter_sweep_returns_ranked_results() -> None:
    config = load_config(Path("config/example.yaml"))
    bars = create_data_feed(config).load()

    results = optimize_moving_average_parameters(
        bars=bars,
        config=config,
        fast_windows=[3, 5],
        slow_windows=[10, 20],
        trade_size=20,
    )

    assert len(results) == 4
    assert results[0].metrics.total_return_pct >= results[-1].metrics.total_return_pct
    assert all(result.fast_window < result.slow_window for result in results)


def test_backtest_run_storage_queries(tmp_path: Path) -> None:
    storage = SQLiteStorage(tmp_path / "backtest_runs.db")
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
    metrics = analyze_backtest(result, config.backtest.initial_cash)
    final_snapshot = result.final_snapshot
    assert final_snapshot is not None

    storage.save_backtest_run(
        created_at="2026-03-07T12:00:00",
        strategy_name=config.strategy.name,
        symbols=config.data.symbols or [config.data.symbol],
        fast_window=config.strategy.fast_window,
        slow_window=config.strategy.slow_window,
        trade_size=config.strategy.trade_size,
        metrics=metrics,
        final_equity=final_snapshot.total_value,
    )

    summary = storage.dashboard_summary()
    latest_runs = storage.latest_backtest_runs(limit=3)
    best_runs = storage.best_backtest_runs(limit=3)

    assert summary.backtest_runs == 1
    assert len(latest_runs) == 1
    assert round(latest_runs[0].sharpe_ratio, 6) == round(metrics.sharpe_ratio, 6)
    assert len(best_runs) == 1
    assert best_runs[0].strategy_name == config.strategy.name


def test_preflight_checks_detect_paper_warning_and_data_pass() -> None:
    config = load_config(Path("config/example.yaml"))
    config.storage.sqlite_path = Path("tmp_preflight.db")
    config.logging.jsonl_path = Path("tmp_logs/runtime.jsonl")
    config.runtime.lock_path = Path("tmp_runtime/runtime.lock")
    config.runtime.state_path = Path("tmp_runtime/state.json")

    checks = run_preflight_checks(config)
    check_map = {check.name: check for check in checks}

    assert check_map["strategy"].status == "PASS"
    assert check_map["data_feed"].status == "PASS"
    assert check_map["filesystem"].status == "PASS"
    assert check_map["broker"].status == "WARN"
