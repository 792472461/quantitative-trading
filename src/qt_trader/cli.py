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
from qt_trader.risk import RiskManager
from qt_trader.runtime import PaperTradingRuntime
from qt_trader.scheduler import SessionScheduler
from qt_trader.storage import SQLiteStorage
from qt_trader.strategy.moving_average import MovingAverageCrossStrategy
from qt_trader.alerts import AlertMessage, AlertNotifier
from qt_trader import __version__

app = typer.Typer(help="Production-oriented quantitative trading CLI.")
console = Console()


def build_strategy(config):
    if config.strategy.name != "moving_average_cross":
        raise ValueError(f"Unsupported strategy: {config.strategy.name}")

    symbols = config.data.symbols or [config.data.symbol]
    return MovingAverageCrossStrategy(
        symbols=symbols,
        fast_window=config.strategy.fast_window,
        slow_window=config.strategy.slow_window,
        trade_size=config.strategy.trade_size,
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


def build_runtime_dependencies(app_config):
    storage = SQLiteStorage(app_config.storage.sqlite_path)
    logger = JsonLogger(app_config.logging.jsonl_path)
    alert_notifier = AlertNotifier(app_config.alert)
    state_store = RuntimeStateStore(app_config.runtime.state_path)
    return storage, logger, alert_notifier, state_store


@app.command()
def backtest(config: Path = typer.Option(..., exists=True, readable=True, help="Path to YAML config.")) -> None:
    app_config = load_config(config)
    bars = create_data_feed(app_config).load()
    portfolio = Portfolio(initial_cash=app_config.backtest.initial_cash)

    engine = BacktestEngine(
        strategy=build_strategy(app_config),
        broker=create_broker(app_config, portfolio=portfolio),
        portfolio=portfolio,
        risk_manager=RiskManager(
            max_position_pct=app_config.backtest.max_position_pct,
            max_drawdown_pct=app_config.backtest.max_drawdown_pct,
            max_total_exposure_pct=app_config.backtest.max_total_exposure_pct,
            max_positions=app_config.backtest.max_positions,
            max_symbol_quantity=app_config.backtest.max_symbol_quantity,
        ),
    )
    result = engine.run(bars)
    final_snapshot = result.final_snapshot
    if final_snapshot is None:
        console.print("[red]No market data loaded.[/red]")
        raise typer.Exit(code=1)

    render_summary("Backtest Summary", final_snapshot, len(result.executed_orders), len(result.rejected_orders))


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
    console.print(
        f"Broker snapshot synced at {synced_at}: "
        f"{len(positions)} positions, {len(orders)} orders for {account.account_id}"
    )


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


@app.command("version")
def version_command() -> None:
    console.print(f"qt-trader {__version__}")


if __name__ == "__main__":
    app()
