from __future__ import annotations

from rich.console import Console
from rich.table import Table

console = Console()


def format_delta(value: float | int | None, precision: int = 2) -> str:
    if value is None:
        return "-"
    return f"{value:+.{precision}f}"


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


def render_signal_watch_result(result) -> None:
    summary = Table(title="Signal Watch Summary")
    summary.add_column("Metric")
    summary.add_column("Value", justify="right")
    summary.add_row("Scanned Bars", str(result.scanned_bars))
    summary.add_row("Latest Bar", "-" if result.latest_timestamp is None else result.latest_timestamp.isoformat())
    summary.add_row("New Alerts", str(len(result.alerted_signals)))
    console.print(summary)

    signal_table = Table(title="New Trade Signals")
    signal_table.add_column("Timestamp")
    signal_table.add_column("Symbol")
    signal_table.add_column("Side")
    signal_table.add_column("Quantity", justify="right")
    signal_table.add_column("Price", justify="right")
    signal_table.add_column("Reason")
    if result.alerted_signals:
        for item in result.alerted_signals:
            signal_table.add_row(
                item.timestamp.isoformat(),
                item.signal.symbol,
                item.signal.side.value,
                str(item.signal.quantity),
                f"{item.price:.2f}",
                item.signal.reason,
            )
    else:
        signal_table.add_row("-", "-", "-", "0", "-", "-")
    console.print(signal_table)


def render_pre_market_review(trading_date: str, previous_trading_date: str, yesterday_buys, signal_result, top_sweeps) -> None:
    overview = Table(title="Pre-Market Review")
    overview.add_column("Metric")
    overview.add_column("Value", justify="right")
    overview.add_row("Trading Date", trading_date)
    overview.add_row("Previous Trading Day", previous_trading_date)
    overview.add_row("Yesterday Buys", str(len(yesterday_buys)))
    overview.add_row("Today Open Signals", str(len(signal_result.alerted_signals)))
    overview.add_row("News Fetch", "pending integration")
    console.print(overview)

    buy_table = Table(title="Yesterday Buy Fills")
    buy_table.add_column("Symbol")
    buy_table.add_column("Quantity", justify="right")
    buy_table.add_column("Price", justify="right")
    buy_table.add_column("Timestamp")
    if yesterday_buys:
        for row in yesterday_buys:
            buy_table.add_row(str(row["symbol"]), str(row["quantity"]), f"{float(row['price']):.2f}", str(row["timestamp"]))
    else:
        buy_table.add_row("-", "0", "-", "-")
    console.print(buy_table)

    signal_table = Table(title="Open Candidate Signals")
    signal_table.add_column("Symbol")
    signal_table.add_column("Side")
    signal_table.add_column("Qty", justify="right")
    signal_table.add_column("Price", justify="right")
    signal_table.add_column("Reason")
    if signal_result.alerted_signals:
        for item in signal_result.alerted_signals:
            signal_table.add_row(
                item.signal.symbol,
                item.signal.side.value,
                str(item.signal.quantity),
                f"{item.price:.2f}",
                item.signal.reason,
            )
    else:
        signal_table.add_row("-", "-", "0", "-", "-")
    console.print(signal_table)

    sweep_table = Table(title="Best Pre-Market Strategy Candidates")
    sweep_table.add_column("Rank", justify="right")
    sweep_table.add_column("MA")
    sweep_table.add_column("Return", justify="right")
    sweep_table.add_column("Sharpe", justify="right")
    sweep_table.add_column("Drawdown", justify="right")
    if top_sweeps:
        for index, item in enumerate(top_sweeps, start=1):
            sweep_table.add_row(
                str(index),
                f"{item.fast_window}/{item.slow_window}",
                f"{item.metrics.total_return_pct:.2f}%",
                f"{item.metrics.sharpe_ratio:.2f}",
                f"{item.metrics.max_drawdown_pct:.2f}%",
            )
    else:
        sweep_table.add_row("-", "-", "-", "-", "-")
    console.print(sweep_table)


def render_post_close_summary(trading_date: str, metrics, final_snapshot, executed_orders: int, rejected_orders: int) -> None:
    table = Table(title="Post-Close Performance")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row("Trading Date", trading_date)
    table.add_row("Final Equity", f"{final_snapshot.total_value:.2f}")
    table.add_row("Total Return", f"{metrics.total_return_pct:.2f}%")
    table.add_row("Max Drawdown", f"{metrics.max_drawdown_pct:.2f}%")
    table.add_row("Filled Orders", str(executed_orders))
    table.add_row("Rejected Orders", str(rejected_orders))
    console.print(table)


def render_live_trade_result(result) -> None:
    summary = Table(title="Live Trading Summary")
    summary.add_column("Metric")
    summary.add_column("Value", justify="right")
    summary.add_row("Scanned Bars", str(result.scanned_bars))
    summary.add_row("Latest Bar", "-" if result.latest_timestamp is None else result.latest_timestamp.isoformat())
    summary.add_row("Submitted Orders", str(len(result.submitted_orders)))
    summary.add_row("Rejected Orders", str(len(result.rejected_orders)))
    console.print(summary)

    order_table = Table(title="Submitted Broker Orders")
    order_table.add_column("Timestamp")
    order_table.add_column("Symbol")
    order_table.add_column("Side")
    order_table.add_column("Quantity", justify="right")
    order_table.add_column("Status")
    order_table.add_column("Reason")
    if result.submitted_orders:
        for item in result.submitted_orders:
            order_table.add_row(
                item.timestamp.isoformat(),
                item.symbol,
                item.side,
                str(item.quantity),
                item.status,
                item.reason,
            )
    else:
        order_table.add_row("-", "-", "-", "0", "-", "-")
    console.print(order_table)


def render_reconciliation_summary(summary) -> None:
    table = Table(title="Broker Reconciliation")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row("Local Submitted Orders", str(summary.local_submitted_orders))
    table.add_row("Local Filled Orders", str(summary.local_filled_orders))
    table.add_row("Local Broker Order IDs", str(summary.local_broker_order_ids))
    table.add_row("Broker Orders", str(summary.broker_orders))
    table.add_row("Broker Trades", str(summary.broker_trades))
    table.add_row("Missing Broker Order IDs", str(summary.missing_broker_order_ids))
    table.add_row("Unmatched Broker Orders", str(summary.unmatched_broker_orders))
    table.add_row("Unmatched Broker Trades", str(summary.unmatched_broker_trades))
    console.print(table)
