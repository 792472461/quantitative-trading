from __future__ import annotations

from pathlib import Path
from datetime import datetime

from rich.console import Console
from rich.table import Table
import typer

from qt_trader.backtest import BacktestEngine
from qt_trader.broker.factory import BrokerConfigurationError, create_broker
from qt_trader.config import load_config
from qt_trader.data.factory import create_data_feed
from qt_trader.market import TradingCalendar
from qt_trader.portfolio import Portfolio
from qt_trader.risk import RiskManager
from qt_trader.runtime import PaperTradingRuntime
from qt_trader.scheduler import SessionScheduler
from qt_trader.storage import SQLiteStorage
from qt_trader.strategy.moving_average import MovingAverageCrossStrategy
from qt_trader import __version__

app = typer.Typer(help="Production-oriented quantitative trading CLI.")
console = Console()


def build_strategy(config):
    if config.strategy.name != "moving_average_cross":
        raise ValueError(f"Unsupported strategy: {config.strategy.name}")

    return MovingAverageCrossStrategy(
        symbol=config.data.symbol,
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


@app.command()
def backtest(config: Path = typer.Option(..., exists=True, readable=True, help="Path to YAML config.")) -> None:
    app_config = load_config(config)
    bars = create_data_feed(app_config).load()

    engine = BacktestEngine(
        strategy=build_strategy(app_config),
        broker=create_broker(app_config),
        portfolio=Portfolio(initial_cash=app_config.backtest.initial_cash),
        risk_manager=RiskManager(
            max_position_pct=app_config.backtest.max_position_pct,
            max_drawdown_pct=app_config.backtest.max_drawdown_pct,
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
    storage = SQLiteStorage(app_config.storage.sqlite_path)

    try:
        broker = create_broker(app_config)
    except BrokerConfigurationError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    runtime = PaperTradingRuntime(
        strategy=build_strategy(app_config),
        broker=broker,
        portfolio=Portfolio(initial_cash=app_config.backtest.initial_cash),
        risk_manager=RiskManager(
            max_position_pct=app_config.backtest.max_position_pct,
            max_drawdown_pct=app_config.backtest.max_drawdown_pct,
        ),
        storage=storage,
        persist_snapshots=app_config.runtime.persist_snapshots,
        sleep_seconds=0.0,
    )
    result = runtime.run(bars)
    final_snapshot = result.snapshots[-1] if result.snapshots else None
    if final_snapshot is None:
        console.print("[red]No market data loaded.[/red]")
        raise typer.Exit(code=1)

    render_summary("Paper Trading Summary", final_snapshot, len(result.executed_orders), len(result.rejected_orders))
    counts = storage.counts()
    console.print(
        f"Persisted to {app_config.storage.sqlite_path}: "
        f"{counts['orders']} orders, {counts['fills']} fills, {counts['snapshots']} snapshots"
    )


@app.command()
def fetch_data(config: Path = typer.Option(..., exists=True, readable=True, help="Path to YAML config.")) -> None:
    app_config = load_config(config)
    bars = create_data_feed(app_config).load()
    console.print(f"Fetched {len(bars)} bars for {app_config.data.symbol} via {app_config.data.provider}.")
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
    storage = SQLiteStorage(app_config.storage.sqlite_path)
    runtime = PaperTradingRuntime(
        strategy=build_strategy(app_config),
        broker=create_broker(app_config),
        portfolio=Portfolio(initial_cash=app_config.backtest.initial_cash),
        risk_manager=RiskManager(
            max_position_pct=app_config.backtest.max_position_pct,
            max_drawdown_pct=app_config.backtest.max_drawdown_pct,
        ),
        storage=storage,
        persist_snapshots=app_config.runtime.persist_snapshots,
        sleep_seconds=0.0,
    )
    result = runtime.run(bars)
    final_snapshot = result.snapshots[-1] if result.snapshots else None
    if final_snapshot is None:
        console.print("[red]No market data loaded.[/red]")
        raise typer.Exit(code=1)

    render_summary("Session Summary", final_snapshot, len(result.executed_orders), len(result.rejected_orders))


@app.command("version")
def version_command() -> None:
    console.print(f"qt-trader {__version__}")


if __name__ == "__main__":
    app()
