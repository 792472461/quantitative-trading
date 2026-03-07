from __future__ import annotations

from dataclasses import dataclass
from math import sqrt

from qt_trader.backtest import BacktestResult
from qt_trader.models import Bar, Fill, OrderSide


@dataclass(slots=True)
class BacktestMetrics:
    total_return_pct: float
    annualized_return_pct: float
    max_drawdown_pct: float
    win_rate_pct: float
    profit_factor: float
    average_win: float
    average_loss: float
    trade_count: int
    equity_volatility_pct: float
    sharpe_ratio: float
    calmar_ratio: float
    expectancy: float


@dataclass(slots=True)
class MarketRegimeMetrics:
    regime: str
    periods: int
    total_return_pct: float
    average_period_return_pct: float
    fill_count: int


def analyze_backtest(result: BacktestResult, initial_cash: float) -> BacktestMetrics:
    snapshots = result.snapshots
    if not snapshots:
        return BacktestMetrics(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0, 0.0, 0.0, 0.0, 0.0)

    final_equity = snapshots[-1].total_value
    total_return = 0.0 if initial_cash == 0 else (final_equity / initial_cash - 1) * 100
    max_drawdown = max(snapshot.drawdown for snapshot in snapshots) * 100
    annualized_return = _annualized_return_pct(snapshots, initial_cash, final_equity)
    period_returns = _equity_returns(snapshots)
    equity_volatility = _equity_volatility_pct(period_returns)
    sharpe_ratio = _sharpe_ratio(period_returns)
    trade_pnls = _round_trip_pnls(result.fills)

    wins = [pnl for pnl in trade_pnls if pnl > 0]
    losses = [pnl for pnl in trade_pnls if pnl < 0]
    trade_count = len(trade_pnls)
    win_rate = 0.0 if trade_count == 0 else len(wins) / trade_count * 100
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = 0.0 if gross_loss == 0 else gross_profit / gross_loss
    average_win = 0.0 if not wins else gross_profit / len(wins)
    average_loss = 0.0 if not losses else abs(sum(losses)) / len(losses)
    expectancy = 0.0 if trade_count == 0 else sum(trade_pnls) / trade_count
    calmar_ratio = 0.0 if max_drawdown == 0 else annualized_return / max_drawdown

    return BacktestMetrics(
        total_return_pct=total_return,
        annualized_return_pct=annualized_return,
        max_drawdown_pct=max_drawdown,
        win_rate_pct=win_rate,
        profit_factor=profit_factor,
        average_win=average_win,
        average_loss=average_loss,
        trade_count=trade_count,
        equity_volatility_pct=equity_volatility,
        sharpe_ratio=sharpe_ratio,
        calmar_ratio=calmar_ratio,
        expectancy=expectancy,
    )


def analyze_market_regimes(
    result: BacktestResult,
    bars: list[Bar],
    benchmark_symbol: str | None,
    fast_window: int,
    slow_window: int,
) -> list[MarketRegimeMetrics]:
    if not benchmark_symbol:
        return []

    benchmark_bars = [bar for bar in bars if bar.symbol == benchmark_symbol]
    if len(benchmark_bars) < slow_window:
        return []

    regime_by_timestamp = _benchmark_regimes(benchmark_bars, fast_window, slow_window)
    if not regime_by_timestamp:
        return []

    stats: dict[str, dict[str, float | int]] = {}
    for previous, current in zip(result.snapshots, result.snapshots[1:]):
        regime = regime_by_timestamp.get(current.timestamp)
        if regime is None or previous.total_value <= 0:
            continue
        period_return = current.total_value / previous.total_value - 1
        bucket = stats.setdefault(
            regime,
            {"periods": 0, "cumulative_factor": 1.0, "sum_returns": 0.0, "fill_count": 0},
        )
        bucket["periods"] = int(bucket["periods"]) + 1
        bucket["cumulative_factor"] = float(bucket["cumulative_factor"]) * (1 + period_return)
        bucket["sum_returns"] = float(bucket["sum_returns"]) + period_return

    fill_regimes: dict[str, int] = {}
    for fill in result.fills:
        regime = regime_by_timestamp.get(fill.timestamp)
        if regime is None:
            continue
        fill_regimes[regime] = fill_regimes.get(regime, 0) + 1

    ordered_regimes = ["bull", "bear", "sideways"]
    metrics: list[MarketRegimeMetrics] = []
    for regime in ordered_regimes:
        bucket = stats.get(regime)
        if bucket is None:
            continue
        periods = int(bucket["periods"])
        cumulative_factor = float(bucket["cumulative_factor"])
        sum_returns = float(bucket["sum_returns"])
        metrics.append(
            MarketRegimeMetrics(
                regime=regime,
                periods=periods,
                total_return_pct=(cumulative_factor - 1) * 100,
                average_period_return_pct=(sum_returns / periods) * 100 if periods else 0.0,
                fill_count=fill_regimes.get(regime, 0),
            )
        )
    return metrics


def _annualized_return_pct(snapshots, initial_cash: float, final_equity: float) -> float:
    if initial_cash <= 0 or len(snapshots) < 2:
        return 0.0
    duration_days = (snapshots[-1].timestamp - snapshots[0].timestamp).days
    if duration_days <= 0:
        return 0.0
    years = duration_days / 365
    return ((final_equity / initial_cash) ** (1 / years) - 1) * 100


def _equity_returns(snapshots) -> list[float]:
    if len(snapshots) < 2:
        return []
    returns: list[float] = []
    for previous, current in zip(snapshots, snapshots[1:]):
        if previous.total_value <= 0:
            continue
        returns.append(current.total_value / previous.total_value - 1)
    return returns


def _equity_volatility_pct(returns: list[float]) -> float:
    if len(returns) < 2:
        return 0.0
    mean = sum(returns) / len(returns)
    variance = sum((value - mean) ** 2 for value in returns) / (len(returns) - 1)
    return sqrt(variance) * 100


def _sharpe_ratio(returns: list[float]) -> float:
    if len(returns) < 2:
        return 0.0
    mean = sum(returns) / len(returns)
    variance = sum((value - mean) ** 2 for value in returns) / (len(returns) - 1)
    if variance <= 0:
        return 0.0
    return mean / sqrt(variance) * sqrt(252)


def _round_trip_pnls(fills: list[Fill]) -> list[float]:
    buy_queues: dict[str, list[tuple[int, float]]] = {}
    trade_pnls: list[float] = []

    for fill in fills:
        if fill.side == OrderSide.BUY:
            buy_queues.setdefault(fill.symbol, []).append((fill.quantity, fill.price + fill.total_fees / fill.quantity))
            continue

        remaining = fill.quantity
        sell_price_net = fill.price - fill.total_fees / fill.quantity
        queue = buy_queues.setdefault(fill.symbol, [])
        while remaining > 0 and queue:
            buy_quantity, buy_price = queue[0]
            matched = min(remaining, buy_quantity)
            trade_pnls.append((sell_price_net - buy_price) * matched)
            remaining -= matched
            buy_quantity -= matched
            if buy_quantity == 0:
                queue.pop(0)
            else:
                queue[0] = (buy_quantity, buy_price)

    return trade_pnls


def _benchmark_regimes(
    benchmark_bars: list[Bar],
    fast_window: int,
    slow_window: int,
) -> dict:
    closes: list[float] = []
    regime_by_timestamp: dict = {}
    for bar in benchmark_bars:
        closes.append(bar.close)
        if len(closes) < slow_window:
            continue
        fast = sum(closes[-fast_window:]) / fast_window
        slow = sum(closes[-slow_window:]) / slow_window
        regime = "sideways"
        if fast > slow:
            regime = "bull"
        elif fast < slow:
            regime = "bear"
        regime_by_timestamp[bar.timestamp] = regime
    return regime_by_timestamp
