from __future__ import annotations

from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.table import Table
import typer

from qt_trader.backtest import BacktestEngine
from qt_trader.broker.factory import BrokerConfigurationError, create_broker
from qt_trader.config import load_config
from qt_trader.data.factory import create_data_feed
from qt_trader.guardian import RuntimeLock, RuntimeLockError, RuntimeStateStore
from qt_trader.market import TradingCalendar
from qt_trader.logging_utils import JsonLogger
from qt_trader.portfolio import Portfolio
from qt_trader.readiness import run_preflight_checks
from qt_trader.research import optimize_moving_average_parameters
from qt_trader.risk import RiskManager
from qt_trader.runtime import PaperTradingRuntime
from qt_trader.scheduler import SessionScheduler
from qt_trader.storage import SQLiteStorage
from qt_trader.strategy.moving_average import MovingAverageCrossStrategy
from qt_trader.alerts import AlertMessage, AlertNotifier
from qt_trader.analytics import analyze_backtest, analyze_market_regimes
from qt_trader import __version__

app = typer.Typer(help="Production-oriented quantitative trading CLI.")
console = Console()


def build_strategy(config):
    if config.strategy.name != "moving_average_cross":
        raise ValueError(f"Unsupported strategy: {config.strategy.name}")

    symbols = config.data.symbols or [config.data.symbol]
    benchmark_symbol = config.strategy.benchmark_symbol
    trade_symbols = [symbol for symbol in symbols if symbol != benchmark_symbol]
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


def render_summary(title: str, final_snapshot, executed_orders: int, rejected_orders: int) -> None:
    summary = Table(title=title)
    summary.add_column("Metric")
    summary.add_column("Value", justify="right")
    summary.add_row("Final Equity", f"{final_snapshot.total_value:.2f}")
    summary.add_row("Cash", f"{final_snapshot.cash:.2f}")
    summary.add_row("Positions Value", f"{final_snapshot.positions_value:.2f}")
    summary.add_row("Drawdown", f"{final_snapshot.drawdown:.2%}")
    summary.add_row("Filled Orders", str(executed_orders))
    summary.add_row("Rejected Orders", str(rejected_orders))
    console.print(summary)


def render_backtest_metrics(metrics) -> None:
    summary = Table(title="Performance Metrics")
    summary.add_column("Metric")
    summary.add_column("Value", justify="right")
    summary.add_row("Total Return", f"{metrics.total_return_pct:.2f}%")
    summary.add_row("Annualized Return", f"{metrics.annualized_return_pct:.2f}%")
    summary.add_row("Max Drawdown", f"{metrics.max_drawdown_pct:.2f}%")
    summary.add_row("Win Rate", f"{metrics.win_rate_pct:.2f}%")
    summary.add_row("Profit Factor", f"{metrics.profit_factor:.2f}")
    summary.add_row("Average Win", f"{metrics.average_win:.2f}")
    summary.add_row("Average Loss", f"{metrics.average_loss:.2f}")
    summary.add_row("Trade Count", str(metrics.trade_count))
    summary.add_row("Equity Volatility", f"{metrics.equity_volatility_pct:.4f}%")
    summary.add_row("Sharpe Ratio", f"{metrics.sharpe_ratio:.2f}")
    summary.add_row("Calmar Ratio", f"{metrics.calmar_ratio:.2f}")
    summary.add_row("Expectancy", f"{metrics.expectancy:.2f}")
    console.print(summary)


def render_market_regime_metrics(regime_metrics) -> None:
    if not regime_metrics:
        return
    table = Table(title="Market Regime Breakdown")
    table.add_column("Regime")
    table.add_column("Periods", justify="right")
    table.add_column("Total Return", justify="right")
    table.add_column("Avg Period Return", justify="right")
    table.add_column("Fills", justify="right")
    for item in regime_metrics:
        table.add_row(
            item.regime,
            str(item.periods),
            f"{item.total_return_pct:.2f}%",
            f"{item.average_period_return_pct:.4f}%",
            str(item.fill_count),
        )
    console.print(table)


def format_delta(value: float | int | None, precision: int = 2) -> str:
    if value is None:
        return "-"
    return f"{value:+.{precision}f}"


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


@app.command()
def backtest(config: Path = typer.Option(..., exists=True, readable=True, help="Path to YAML config.")) -> None:
    app_config = load_config(config)
    bars = create_data_feed(app_config).load()
    portfolio = Portfolio(initial_cash=app_config.backtest.initial_cash)
    storage = SQLiteStorage(app_config.storage.sqlite_path)

    engine = BacktestEngine(
        strategy=build_strategy(app_config),
        broker=create_broker(app_config, portfolio=portfolio),
        portfolio=portfolio,
        risk_manager=build_risk_manager(app_config),
    )
    result = engine.run(bars)
    final_snapshot = result.final_snapshot
    if final_snapshot is None:
        console.print("[red]No market data loaded.[/red]")
        raise typer.Exit(code=1)

    render_summary("Backtest Summary", final_snapshot, len(result.executed_orders), len(result.rejected_orders))
    metrics = analyze_backtest(result, app_config.backtest.initial_cash)
    render_backtest_metrics(metrics)
    render_market_regime_metrics(
        analyze_market_regimes(
            result=result,
            bars=bars,
            benchmark_symbol=app_config.strategy.benchmark_symbol,
            fast_window=app_config.strategy.market_fast_window,
            slow_window=app_config.strategy.market_slow_window,
        )
    )
    persist_backtest_run(storage, app_config, metrics, final_snapshot.total_value)
    console.print(f"Backtest run stored in {app_config.storage.sqlite_path}")


@app.command()
def paper_trade(config: Path = typer.Option(..., exists=True, readable=True, help="Path to YAML config.")) -> None:
    app_config = load_config(config)
    bars = create_data_feed(app_config).load()
    storage, logger, alert_notifier, state_store = build_runtime_dependencies(app_config)
    portfolio = Portfolio(initial_cash=app_config.backtest.initial_cash)

    try:
        broker = create_broker(app_config, portfolio=portfolio)
    except BrokerConfigurationError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    try:
        with RuntimeLock(app_config.runtime.lock_path):
            runtime = PaperTradingRuntime(
                strategy=build_strategy(app_config),
                broker=broker,
                portfolio=portfolio,
                risk_manager=RiskManager(
                    max_position_pct=app_config.backtest.max_position_pct,
                    max_drawdown_pct=app_config.backtest.max_drawdown_pct,
                    max_total_exposure_pct=app_config.backtest.max_total_exposure_pct,
                    max_positions=app_config.backtest.max_positions,
                    max_symbol_quantity=app_config.backtest.max_symbol_quantity,
                ),
                storage=storage,
                persist_snapshots=app_config.runtime.persist_snapshots,
                sleep_seconds=0.0,
                logger=logger,
                alert_notifier=alert_notifier,
                max_drawdown_alert_pct=app_config.alert.max_drawdown_pct,
                rejected_order_alert_threshold=app_config.alert.rejected_order_threshold,
                state_store=state_store,
            )
            result = runtime.run(bars)
    except RuntimeLockError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    final_snapshot = result.snapshots[-1] if result.snapshots else None
    if final_snapshot is None:
        console.print("[red]No market data loaded.[/red]")
        raise typer.Exit(code=1)

    render_summary("Paper Trading Summary", final_snapshot, len(result.executed_orders), len(result.rejected_orders))
    counts = storage.counts()
    console.print(
        f"Persisted to {app_config.storage.sqlite_path}: "
        f"{counts['orders']} orders, {counts['fills']} fills, "
        f"{counts['snapshots']} snapshots, {counts['events']} events"
    )
    console.print(f"Structured log written to {app_config.logging.jsonl_path}")


@app.command()
def fetch_data(config: Path = typer.Option(..., exists=True, readable=True, help="Path to YAML config.")) -> None:
    app_config = load_config(config)
    bars = create_data_feed(app_config).load()
    symbols = app_config.data.symbols or [app_config.data.symbol]
    console.print(f"Fetched {len(bars)} bars for {', '.join(symbols)} via {app_config.data.provider}.")
    if app_config.data.output_csv_path is not None:
        console.print(f"Saved normalized CSV to {app_config.data.output_csv_path}")


@app.command()
def market_status(
    config: Path = typer.Option(..., exists=True, readable=True, help="Path to YAML config."),
    at: str | None = typer.Option(None, help="Optional local time, format: YYYY-MM-DDTHH:MM:SS"),
) -> None:
    app_config = load_config(config)
    calendar = TradingCalendar(app_config.market)
    current_time = datetime.fromisoformat(at) if at else None
    status = calendar.status(current_time)

    summary = Table(title="Market Status")
    summary.add_column("Metric")
    summary.add_column("Value", justify="right")
    summary.add_row("Timezone", app_config.market.timezone)
    summary.add_row("Current Time", status.current_time.isoformat())
    summary.add_row("Trading Day", str(status.is_trading_day))
    summary.add_row("Market Open", str(status.is_open))
    summary.add_row("Phase", status.phase)
    summary.add_row("Next Open", status.next_open.isoformat())
    console.print(summary)


@app.command()
def run_session(
    config: Path = typer.Option(..., exists=True, readable=True, help="Path to YAML config."),
    force: bool = typer.Option(False, help="Run even if market is currently closed."),
) -> None:
    app_config = load_config(config)
    scheduler = SessionScheduler(TradingCalendar(app_config.market))
    if not force and not scheduler.should_run_now():
        console.print(f"[yellow]Session blocked: {scheduler.describe()}[/yellow]")
        raise typer.Exit(code=1)

    bars = create_data_feed(app_config).load()
    storage, logger, alert_notifier, state_store = build_runtime_dependencies(app_config)
    attempts = 0
    result = None
    portfolio = Portfolio(initial_cash=app_config.backtest.initial_cash)
    try:
        with RuntimeLock(app_config.runtime.lock_path):
            while attempts <= app_config.runtime.max_retries:
                attempts += 1
                try:
                    broker = create_broker(app_config, portfolio=portfolio)
                    runtime = PaperTradingRuntime(
                        strategy=build_strategy(app_config),
                        broker=broker,
                        portfolio=portfolio,
                        risk_manager=RiskManager(
                            max_position_pct=app_config.backtest.max_position_pct,
                            max_drawdown_pct=app_config.backtest.max_drawdown_pct,
                            max_total_exposure_pct=app_config.backtest.max_total_exposure_pct,
                            max_positions=app_config.backtest.max_positions,
                            max_symbol_quantity=app_config.backtest.max_symbol_quantity,
                        ),
                        storage=storage,
                        persist_snapshots=app_config.runtime.persist_snapshots,
                        sleep_seconds=0.0,
                        logger=logger,
                        alert_notifier=alert_notifier,
                        max_drawdown_alert_pct=app_config.alert.max_drawdown_pct,
                        rejected_order_alert_threshold=app_config.alert.rejected_order_threshold,
                        state_store=state_store,
                    )
                    result = runtime.run(bars)
                    break
                except Exception as exc:  # noqa: BLE001
                    state_store.mark_failed(str(exc), attempts)
                    if attempts > app_config.runtime.max_retries:
                        raise
    except RuntimeLockError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        console.print(f"[red]Session failed after {attempts} attempt(s): {exc}[/red]")
        raise typer.Exit(code=1) from exc
    if result is None:
        console.print("[red]No runtime result produced.[/red]")
        raise typer.Exit(code=1)
    final_snapshot = result.snapshots[-1] if result.snapshots else None
    if final_snapshot is None:
        console.print("[red]No market data loaded.[/red]")
        raise typer.Exit(code=1)

    render_summary("Session Summary", final_snapshot, len(result.executed_orders), len(result.rejected_orders))


@app.command()
def runtime_state(config: Path = typer.Option(..., exists=True, readable=True, help="Path to YAML config.")) -> None:
    app_config = load_config(config)
    state = RuntimeStateStore(app_config.runtime.state_path).load()
    summary = Table(title="Runtime State")
    summary.add_column("Metric")
    summary.add_column("Value", justify="right")
    summary.add_row("Last Status", state.last_status)
    summary.add_row("Started At", state.last_run_started_at or "-")
    summary.add_row("Completed At", state.last_run_completed_at or "-")
    summary.add_row("Retry Count", str(state.retry_count))
    summary.add_row("Last Error", state.last_error or "-")
    console.print(summary)


@app.command()
def broker_account(config: Path = typer.Option(..., exists=True, readable=True, help="Path to YAML config.")) -> None:
    app_config = load_config(config)
    portfolio = Portfolio(initial_cash=app_config.backtest.initial_cash)
    broker = create_broker(app_config, portfolio=portfolio)
    account = broker.get_account_info()
    positions = broker.get_positions()
    orders = broker.get_orders()

    account_table = Table(title="Broker Account")
    account_table.add_column("Metric")
    account_table.add_column("Value", justify="right")
    account_table.add_row("Broker", account.broker)
    account_table.add_row("Account ID", account.account_id)
    account_table.add_row("Environment", account.environment)
    account_table.add_row("Cash", f"{account.cash:.2f}")
    account_table.add_row("Total Equity", f"{account.total_equity:.2f}")
    account_table.add_row("Buying Power", f"{account.buying_power:.2f}")
    console.print(account_table)

    position_table = Table(title="Broker Positions")
    position_table.add_column("Symbol")
    position_table.add_column("Quantity", justify="right")
    position_table.add_column("Avg Cost", justify="right")
    position_table.add_column("Market Value", justify="right")
    if positions:
        for position in positions:
            position_table.add_row(
                position.symbol,
                str(position.quantity),
                f"{position.average_cost:.2f}",
                f"{position.market_value:.2f}",
            )
    else:
        position_table.add_row("-", "0", "0.00", "0.00")
    console.print(position_table)

    order_table = Table(title="Broker Orders")
    order_table.add_column("Symbol")
    order_table.add_column("Side")
    order_table.add_column("Quantity", justify="right")
    order_table.add_column("Status")
    if orders:
        for order in orders[-5:]:
            order_table.add_row(order.symbol, order.side, str(order.quantity), order.status)
    else:
        order_table.add_row("-", "-", "0", "-")
    console.print(order_table)


@app.command()
def broker_sync(config: Path = typer.Option(..., exists=True, readable=True, help="Path to YAML config.")) -> None:
    app_config = load_config(config)
    storage = SQLiteStorage(app_config.storage.sqlite_path)
    portfolio = Portfolio(initial_cash=app_config.backtest.initial_cash)
    broker = create_broker(app_config, portfolio=portfolio)
    account = broker.get_account_info()
    positions = broker.get_positions()
    orders = broker.get_orders()
    synced_at = datetime.now().isoformat()
    storage.save_broker_snapshot(account, positions, orders, synced_at)
    summary = storage.latest_broker_sync_summary(account.account_id)
    console.print(
        f"Broker snapshot synced at {synced_at}: "
        f"{len(positions)} positions, {len(orders)} orders for {account.account_id}"
    )
    if summary is None:
        return

    summary_table = Table(title="Broker Sync Delta")
    summary_table.add_column("Metric")
    summary_table.add_column("Value", justify="right")
    summary_table.add_row("Previous Sync", summary.previous_synced_at or "-")
    summary_table.add_row("Cash Change", format_delta(summary.cash_change))
    summary_table.add_row("Equity Change", format_delta(summary.total_equity_change))
    summary_table.add_row("Buying Power Change", format_delta(summary.buying_power_change))
    summary_table.add_row("Position Added", str(summary.position_added))
    summary_table.add_row("Position Removed", str(summary.position_removed))
    summary_table.add_row("Position Updated", str(summary.position_changed))
    summary_table.add_row("Broker Orders", str(summary.broker_order_count))
    summary_table.add_row("Broker Order Delta", "-" if summary.broker_order_change is None else str(summary.broker_order_change))
    console.print(summary_table)

    position_changes = storage.latest_broker_position_changes(account.account_id, limit=5)
    if position_changes:
        position_table = Table(title="Latest Position Changes")
        position_table.add_column("Symbol")
        position_table.add_column("Status")
        position_table.add_column("Qty Delta", justify="right")
        position_table.add_column("Value Delta", justify="right")
        for change in position_changes:
            position_table.add_row(
                change.symbol,
                change.status,
                format_delta(change.quantity_change, precision=0),
                format_delta(change.market_value_change),
            )
        console.print(position_table)


@app.command()
def dashboard(
    config: Path = typer.Option(..., exists=True, readable=True, help="Path to YAML config."),
    event_limit: int = typer.Option(5, min=1, max=50, help="Number of recent events to display."),
) -> None:
    app_config = load_config(config)
    storage = SQLiteStorage(app_config.storage.sqlite_path)
    summary = storage.dashboard_summary()

    overview = Table(title="Dashboard Overview")
    overview.add_column("Metric")
    overview.add_column("Value", justify="right")
    overview.add_row("Orders", str(summary.orders))
    overview.add_row("Fills", str(summary.fills))
    overview.add_row("Events", str(summary.events))
    overview.add_row("Backtest Runs", str(summary.backtest_runs))
    overview.add_row("Synced Accounts", str(summary.synced_accounts))
    overview.add_row("Synced Positions", str(summary.synced_positions))
    overview.add_row("Synced Broker Orders", str(summary.synced_broker_orders))
    overview.add_row("Latest Equity", "-" if summary.latest_equity is None else f"{summary.latest_equity:.2f}")
    overview.add_row("Latest Cash", "-" if summary.latest_cash is None else f"{summary.latest_cash:.2f}")
    overview.add_row("Latest Drawdown", "-" if summary.latest_drawdown is None else f"{summary.latest_drawdown:.2%}")
    console.print(overview)

    broker_account_snapshot = storage.latest_broker_account()
    broker_table = Table(title="Latest Synced Broker Account")
    broker_table.add_column("Metric")
    broker_table.add_column("Value", justify="right")
    if broker_account_snapshot is not None:
        broker_table.add_row("Synced At", str(broker_account_snapshot["synced_at"]))
        broker_table.add_row("Account ID", str(broker_account_snapshot["account_id"]))
        broker_table.add_row("Broker", str(broker_account_snapshot["broker"]))
        broker_table.add_row("Environment", str(broker_account_snapshot["environment"]))
        broker_table.add_row("Cash", f"{float(broker_account_snapshot['cash']):.2f}")
        broker_table.add_row("Total Equity", f"{float(broker_account_snapshot['total_equity']):.2f}")
    else:
        broker_table.add_row("Synced At", "-")
        broker_table.add_row("Account ID", "-")
        broker_table.add_row("Broker", "-")
        broker_table.add_row("Environment", "-")
        broker_table.add_row("Cash", "-")
        broker_table.add_row("Total Equity", "-")
    console.print(broker_table)

    broker_sync_summary = storage.latest_broker_sync_summary()
    broker_change_table = Table(title="Latest Broker Sync Delta")
    broker_change_table.add_column("Metric")
    broker_change_table.add_column("Value", justify="right")
    if broker_sync_summary is not None:
        broker_change_table.add_row("Current Sync", broker_sync_summary.synced_at)
        broker_change_table.add_row("Previous Sync", broker_sync_summary.previous_synced_at or "-")
        broker_change_table.add_row("Cash Change", format_delta(broker_sync_summary.cash_change))
        broker_change_table.add_row("Equity Change", format_delta(broker_sync_summary.total_equity_change))
        broker_change_table.add_row("Position Added", str(broker_sync_summary.position_added))
        broker_change_table.add_row("Position Removed", str(broker_sync_summary.position_removed))
        broker_change_table.add_row("Position Updated", str(broker_sync_summary.position_changed))
        broker_change_table.add_row(
            "Broker Order Delta",
            "-" if broker_sync_summary.broker_order_change is None else str(broker_sync_summary.broker_order_change),
        )
    else:
        broker_change_table.add_row("Current Sync", "-")
        broker_change_table.add_row("Previous Sync", "-")
        broker_change_table.add_row("Cash Change", "-")
        broker_change_table.add_row("Equity Change", "-")
        broker_change_table.add_row("Position Added", "0")
        broker_change_table.add_row("Position Removed", "0")
        broker_change_table.add_row("Position Updated", "0")
        broker_change_table.add_row("Broker Order Delta", "-")
    console.print(broker_change_table)

    broker_position_changes = storage.latest_broker_position_changes(limit=5)
    broker_position_change_table = Table(title="Latest Broker Position Changes")
    broker_position_change_table.add_column("Symbol")
    broker_position_change_table.add_column("Status")
    broker_position_change_table.add_column("Qty Delta", justify="right")
    broker_position_change_table.add_column("Value Delta", justify="right")
    if broker_position_changes:
        for change in broker_position_changes:
            broker_position_change_table.add_row(
                change.symbol,
                change.status,
                format_delta(change.quantity_change, precision=0),
                format_delta(change.market_value_change),
            )
    else:
        broker_position_change_table.add_row("-", "-", "-", "-")
    console.print(broker_position_change_table)

    latest_backtests = storage.latest_backtest_runs(limit=5)
    latest_backtest_table = Table(title="Latest Backtest Runs")
    latest_backtest_table.add_column("Created At")
    latest_backtest_table.add_column("MA")
    latest_backtest_table.add_column("Return", justify="right")
    latest_backtest_table.add_column("Sharpe", justify="right")
    latest_backtest_table.add_column("Drawdown", justify="right")
    if latest_backtests:
        for run in latest_backtests:
            latest_backtest_table.add_row(
                run.created_at,
                f"{run.fast_window}/{run.slow_window}",
                f"{run.total_return_pct:.2f}%",
                f"{run.sharpe_ratio:.2f}",
                f"{run.max_drawdown_pct:.2f}%",
            )
    else:
        latest_backtest_table.add_row("-", "-", "-", "-", "-")
    console.print(latest_backtest_table)

    best_backtests = storage.best_backtest_runs(limit=5)
    best_backtest_table = Table(title="Top Backtest Runs")
    best_backtest_table.add_column("MA")
    best_backtest_table.add_column("Trade Size", justify="right")
    best_backtest_table.add_column("Return", justify="right")
    best_backtest_table.add_column("Sharpe", justify="right")
    best_backtest_table.add_column("Calmar", justify="right")
    if best_backtests:
        for run in best_backtests:
            best_backtest_table.add_row(
                f"{run.fast_window}/{run.slow_window}",
                str(run.trade_size),
                f"{run.total_return_pct:.2f}%",
                f"{run.sharpe_ratio:.2f}",
                f"{run.calmar_ratio:.2f}",
            )
    else:
        best_backtest_table.add_row("-", "-", "-", "-", "-")
    console.print(best_backtest_table)

    symbol_rows = storage.symbol_fill_summary()
    symbol_table = Table(title="Fill Summary By Symbol")
    symbol_table.add_column("Symbol")
    symbol_table.add_column("Fills", justify="right")
    symbol_table.add_column("Quantity", justify="right")
    symbol_table.add_column("Fees", justify="right")
    if symbol_rows:
        for row in symbol_rows:
            symbol_table.add_row(
                str(row["symbol"]),
                str(row["fill_count"]),
                str(row["total_quantity"]),
                f"{float(row['total_fees']):.2f}",
            )
    else:
        symbol_table.add_row("-", "0", "0", "0.00")
    console.print(symbol_table)

    event_rows = storage.recent_events(event_limit)
    event_table = Table(title="Recent Events")
    event_table.add_column("Timestamp")
    event_table.add_column("Severity")
    event_table.add_column("Type")
    event_table.add_column("Message")
    if event_rows:
        for row in event_rows:
            event_table.add_row(row["timestamp"], row["severity"], row["event_type"], row["message"])
    else:
        event_table.add_row("-", "-", "-", "-")
    console.print(event_table)


@app.command()
def send_test_alert(config: Path = typer.Option(..., exists=True, readable=True, help="Path to YAML config.")) -> None:
    app_config = load_config(config)
    notifier = AlertNotifier(app_config.alert)
    notifier.send(AlertMessage(severity="INFO", title="Test alert", body="Manual alert pipeline check"))
    console.print("Test alert sent.")


@app.command()
def optimize_strategy(
    config: Path = typer.Option(..., exists=True, readable=True, help="Path to YAML config."),
    fast_windows: str = typer.Option("3,5,8", help="Comma separated fast MA windows."),
    slow_windows: str = typer.Option("15,20,30", help="Comma separated slow MA windows."),
    top_n: int = typer.Option(5, min=1, max=20, help="Number of top runs to display."),
    trade_size: int | None = typer.Option(None, min=1, help="Optional trade size override."),
) -> None:
    app_config = load_config(config)
    bars = create_data_feed(app_config).load()
    try:
        fast_values = parse_int_list(fast_windows)
        slow_values = parse_int_list(slow_windows)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    results = optimize_moving_average_parameters(
        bars=bars,
        config=app_config,
        fast_windows=fast_values,
        slow_windows=slow_values,
        trade_size=trade_size,
    )
    if not results:
        console.print("[red]No valid parameter combinations found.[/red]")
        raise typer.Exit(code=1)

    storage = SQLiteStorage(app_config.storage.sqlite_path)
    resolved_trade_size = trade_size or app_config.strategy.trade_size
    symbols = app_config.data.symbols or [app_config.data.symbol]
    for result in results:
        storage.save_backtest_run(
            created_at=datetime.now().isoformat(),
            strategy_name=app_config.strategy.name,
            symbols=symbols,
            fast_window=result.fast_window,
            slow_window=result.slow_window,
            trade_size=resolved_trade_size,
            metrics=result.metrics,
            final_equity=app_config.backtest.initial_cash * (1 + result.metrics.total_return_pct / 100),
        )

    table = Table(title="Moving Average Parameter Sweep")
    table.add_column("Rank", justify="right")
    table.add_column("MA")
    table.add_column("Trade Size", justify="right")
    table.add_column("Return", justify="right")
    table.add_column("Sharpe", justify="right")
    table.add_column("Drawdown", justify="right")
    table.add_column("Trades", justify="right")
    table.add_column("Expectancy", justify="right")
    for index, result in enumerate(results[:top_n], start=1):
        table.add_row(
            str(index),
            f"{result.fast_window}/{result.slow_window}",
            str(result.trade_size),
            f"{result.metrics.total_return_pct:.2f}%",
            f"{result.metrics.sharpe_ratio:.2f}",
            f"{result.metrics.max_drawdown_pct:.2f}%",
            str(result.metrics.trade_count),
            f"{result.metrics.expectancy:.2f}",
        )
    console.print(table)
    console.print(f"Stored {len(results)} sweep runs in {app_config.storage.sqlite_path}")


@app.command()
def preflight_check(config: Path = typer.Option(..., exists=True, readable=True, help="Path to YAML config.")) -> None:
    app_config = load_config(config)
    checks = run_preflight_checks(app_config)

    table = Table(title="Preflight Checks")
    table.add_column("Check")
    table.add_column("Status")
    table.add_column("Message")
    for check in checks:
        status_color = {"PASS": "green", "WARN": "yellow", "FAIL": "red"}.get(check.status, "white")
        table.add_row(check.name, f"[{status_color}]{check.status}[/{status_color}]", check.message)
    console.print(table)

    failures = [check for check in checks if check.status == "FAIL"]
    if failures:
        raise typer.Exit(code=1)


@app.command("version")
def version_command() -> None:
    console.print(f"qt-trader {__version__}")


if __name__ == "__main__":
    app()
