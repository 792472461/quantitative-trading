from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from qt_trader.models import AccountInfo, Fill, Order, OrderInfo, OrderSide, PortfolioSnapshot, PositionInfo, RuntimeEvent, TradeInfo


@dataclass(slots=True)
class DashboardSummary:
    orders: int
    fills: int
    events: int
    backtest_runs: int
    synced_accounts: int
    synced_positions: int
    synced_broker_orders: int
    latest_equity: float | None
    latest_cash: float | None
    latest_drawdown: float | None


@dataclass(slots=True)
class BrokerSyncSummary:
    account_id: str
    broker: str
    environment: str
    synced_at: str
    previous_synced_at: str | None
    cash: float
    total_equity: float
    buying_power: float
    cash_change: float | None
    total_equity_change: float | None
    buying_power_change: float | None
    position_count: int
    position_added: int
    position_removed: int
    position_changed: int
    broker_order_count: int
    broker_order_change: int | None


@dataclass(slots=True)
class BrokerPositionChange:
    symbol: str
    status: str
    previous_quantity: int
    current_quantity: int
    quantity_change: int
    previous_market_value: float
    current_market_value: float
    market_value_change: float


@dataclass(slots=True)
class BacktestRunRecord:
    created_at: str
    strategy_name: str
    symbols: str
    fast_window: int
    slow_window: int
    trade_size: int
    total_return_pct: float
    annualized_return_pct: float
    max_drawdown_pct: float
    win_rate_pct: float
    profit_factor: float
    trade_count: int
    sharpe_ratio: float
    calmar_ratio: float
    expectancy: float
    final_equity: float


@dataclass(slots=True)
class DailyPerformanceRecord:
    trading_date: str
    created_at: str
    total_return_pct: float
    max_drawdown_pct: float
    final_equity: float
    filled_orders: int
    rejected_orders: int


@dataclass(slots=True)
class ReconciliationSummary:
    local_submitted_orders: int
    local_partial_orders: int
    local_filled_orders: int
    local_canceled_orders: int
    local_broker_order_ids: int
    broker_orders: int
    broker_trades: int
    missing_broker_order_ids: int
    unmatched_broker_orders: int
    unmatched_broker_trades: int


class SQLiteStorage:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    timestamp TEXT NOT NULL,
                    price REAL,
                    status TEXT NOT NULL,
                    broker_order_id TEXT NOT NULL DEFAULT '',
                    reason TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS fills (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    price REAL NOT NULL,
                    timestamp TEXT NOT NULL,
                    broker_order_id TEXT NOT NULL DEFAULT '',
                    commission REAL NOT NULL,
                    stamp_duty REAL NOT NULL,
                    slippage_cost REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    cash REAL NOT NULL,
                    total_value REAL NOT NULL,
                    positions_value REAL NOT NULL,
                    drawdown REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    message TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS broker_accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    synced_at TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    broker TEXT NOT NULL,
                    cash REAL NOT NULL,
                    total_equity REAL NOT NULL,
                    buying_power REAL NOT NULL,
                    environment TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS broker_positions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    synced_at TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    average_cost REAL NOT NULL,
                    market_price REAL NOT NULL,
                    market_value REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS broker_orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    synced_at TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    price REAL,
                    status TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    broker_order_id TEXT NOT NULL DEFAULT '',
                    reason TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS broker_trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    synced_at TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    price REAL NOT NULL,
                    timestamp TEXT NOT NULL,
                    broker_order_id TEXT NOT NULL DEFAULT '',
                    trade_id TEXT NOT NULL DEFAULT '',
                    reason TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS backtest_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    strategy_name TEXT NOT NULL,
                    symbols TEXT NOT NULL,
                    fast_window INTEGER NOT NULL,
                    slow_window INTEGER NOT NULL,
                    trade_size INTEGER NOT NULL,
                    total_return_pct REAL NOT NULL,
                    annualized_return_pct REAL NOT NULL,
                    max_drawdown_pct REAL NOT NULL,
                    win_rate_pct REAL NOT NULL,
                    profit_factor REAL NOT NULL,
                    average_win REAL NOT NULL,
                    average_loss REAL NOT NULL,
                    trade_count INTEGER NOT NULL,
                    equity_volatility_pct REAL NOT NULL,
                    sharpe_ratio REAL NOT NULL,
                    calmar_ratio REAL NOT NULL,
                    expectancy REAL NOT NULL,
                    final_equity REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS daily_performance (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trading_date TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    total_return_pct REAL NOT NULL,
                    max_drawdown_pct REAL NOT NULL,
                    final_equity REAL NOT NULL,
                    filled_orders INTEGER NOT NULL,
                    rejected_orders INTEGER NOT NULL
                )
                """
            )
            self._ensure_fill_columns(conn)

    def _ensure_fill_columns(self, conn: sqlite3.Connection) -> None:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(fills)").fetchall()}
        if "broker_order_id" not in columns:
            conn.execute("ALTER TABLE fills ADD COLUMN broker_order_id TEXT NOT NULL DEFAULT ''")
        if "stamp_duty" not in columns:
            conn.execute("ALTER TABLE fills ADD COLUMN stamp_duty REAL NOT NULL DEFAULT 0")
        if "slippage_cost" not in columns:
            conn.execute("ALTER TABLE fills ADD COLUMN slippage_cost REAL NOT NULL DEFAULT 0")

        order_columns = {row[1] for row in conn.execute("PRAGMA table_info(orders)").fetchall()}
        if "broker_order_id" not in order_columns:
            conn.execute("ALTER TABLE orders ADD COLUMN broker_order_id TEXT NOT NULL DEFAULT ''")

        broker_order_columns = {row[1] for row in conn.execute("PRAGMA table_info(broker_orders)").fetchall()}
        if "broker_order_id" not in broker_order_columns:
            conn.execute("ALTER TABLE broker_orders ADD COLUMN broker_order_id TEXT NOT NULL DEFAULT ''")

        trade_columns = {row[1] for row in conn.execute("PRAGMA table_info(broker_trades)").fetchall()}
        if "trade_id" not in trade_columns:
            conn.execute("ALTER TABLE broker_trades ADD COLUMN trade_id TEXT NOT NULL DEFAULT ''")
        if "broker_order_id" not in trade_columns:
            conn.execute("ALTER TABLE broker_trades ADD COLUMN broker_order_id TEXT NOT NULL DEFAULT ''")

    def save_order(self, order: Order) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO orders (symbol, side, quantity, timestamp, price, status, broker_order_id, reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    order.symbol,
                    order.side.value,
                    order.quantity,
                    order.timestamp.isoformat(),
                    order.price,
                    order.status.value,
                    order.broker_order_id,
                    order.reason,
                ),
            )

    def save_fill(self, fill: Fill) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO fills (symbol, side, quantity, price, timestamp, broker_order_id, commission, stamp_duty, slippage_cost)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fill.symbol,
                    fill.side.value,
                    fill.quantity,
                    fill.price,
                    fill.timestamp.isoformat(),
                    fill.broker_order_id,
                    fill.commission,
                    fill.stamp_duty,
                    fill.slippage_cost,
                ),
            )

    def save_fill_if_missing(self, fill: Fill, trade_id: str = "") -> bool:
        with self._connect() as conn:
            if trade_id:
                existing = conn.execute(
                    """
                    SELECT 1
                    FROM broker_trades
                    WHERE trade_id = ?
                    LIMIT 1
                    """,
                    (trade_id,),
                ).fetchone()
                if existing is not None:
                    return False
            existing = conn.execute(
                """
                SELECT 1
                FROM fills
                WHERE broker_order_id = ? AND symbol = ? AND quantity = ? AND price = ? AND timestamp = ?
                LIMIT 1
                """,
                (
                    fill.broker_order_id,
                    fill.symbol,
                    fill.quantity,
                    fill.price,
                    fill.timestamp.isoformat(),
                ),
            ).fetchone()
            if existing is not None:
                return False
            self.save_fill(fill)
            return True

    def update_order_status(
        self,
        *,
        broker_order_id: str,
        status: str,
        reason: str | None = None,
    ) -> int:
        if not broker_order_id.strip():
            return 0
        with self._connect() as conn:
            result = conn.execute(
                """
                UPDATE orders
                SET status = ?, reason = CASE WHEN ? IS NULL OR ? = '' THEN reason ELSE ? END
                WHERE broker_order_id = ?
                """,
                (status, reason, reason, reason, broker_order_id),
            )
            return int(result.rowcount)

    def attach_broker_order_id(
        self,
        *,
        symbol: str,
        timestamp: datetime,
        broker_order_id: str,
        status: str | None = None,
    ) -> int:
        if not broker_order_id.strip():
            return 0
        with self._connect() as conn:
            result = conn.execute(
                """
                UPDATE orders
                SET broker_order_id = ?, status = COALESCE(?, status)
                WHERE id = (
                    SELECT id
                    FROM orders
                    WHERE symbol = ? AND timestamp = ? AND broker_order_id = ''
                    ORDER BY id DESC
                    LIMIT 1
                )
                """,
                (broker_order_id, status, symbol, timestamp.isoformat()),
            )
            return int(result.rowcount)

    def save_snapshot(self, snapshot: PortfolioSnapshot) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO snapshots (timestamp, cash, total_value, positions_value, drawdown)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    snapshot.timestamp.isoformat(),
                    snapshot.cash,
                    snapshot.total_value,
                    snapshot.positions_value,
                    snapshot.drawdown,
                ),
            )

    def save_event(self, event: RuntimeEvent) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO events (event_type, timestamp, severity, message)
                VALUES (?, ?, ?, ?)
                """,
                (
                    event.event_type,
                    event.timestamp.isoformat(),
                    event.severity,
                    event.message,
                ),
            )

    def counts(self) -> dict[str, int]:
        with self._connect() as conn:
            orders = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
            fills = conn.execute("SELECT COUNT(*) FROM fills").fetchone()[0]
            snapshots = conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
            events = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            backtest_runs = conn.execute("SELECT COUNT(*) FROM backtest_runs").fetchone()[0]
            broker_accounts = conn.execute("SELECT COUNT(*) FROM broker_accounts").fetchone()[0]
            broker_positions = conn.execute("SELECT COUNT(*) FROM broker_positions").fetchone()[0]
            broker_orders = conn.execute("SELECT COUNT(*) FROM broker_orders").fetchone()[0]
            broker_trades = conn.execute("SELECT COUNT(*) FROM broker_trades").fetchone()[0]
            daily_performance = conn.execute("SELECT COUNT(*) FROM daily_performance").fetchone()[0]
        return {
            "orders": orders,
            "fills": fills,
            "snapshots": snapshots,
            "events": events,
            "backtest_runs": backtest_runs,
            "broker_accounts": broker_accounts,
            "broker_positions": broker_positions,
            "broker_orders": broker_orders,
            "broker_trades": broker_trades,
            "daily_performance": daily_performance,
        }

    def save_daily_performance(
        self,
        *,
        trading_date: str,
        created_at: str,
        total_return_pct: float,
        max_drawdown_pct: float,
        final_equity: float,
        filled_orders: int,
        rejected_orders: int,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO daily_performance (
                    trading_date,
                    created_at,
                    total_return_pct,
                    max_drawdown_pct,
                    final_equity,
                    filled_orders,
                    rejected_orders
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trading_date,
                    created_at,
                    total_return_pct,
                    max_drawdown_pct,
                    final_equity,
                    filled_orders,
                    rejected_orders,
                ),
            )

    def latest_daily_performance(self, limit: int = 5) -> list[DailyPerformanceRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT trading_date, created_at, total_return_pct, max_drawdown_pct, final_equity, filled_orders, rejected_orders
                FROM daily_performance
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            DailyPerformanceRecord(
                trading_date=str(row[0]),
                created_at=str(row[1]),
                total_return_pct=float(row[2]),
                max_drawdown_pct=float(row[3]),
                final_equity=float(row[4]),
                filled_orders=int(row[5]),
                rejected_orders=int(row[6]),
            )
            for row in rows
        ]

    def fills_on_date(self, trading_date: str, side: str | None = None) -> list[dict[str, object]]:
        sql = """
            SELECT symbol, side, quantity, price, timestamp, commission, stamp_duty
            FROM fills
            WHERE substr(timestamp, 1, 10) = ?
        """
        params: list[object] = [trading_date]
        if side is not None:
            sql += " AND side = ?"
            params.append(side)
        sql += " ORDER BY id ASC"
        with self._connect() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [
            {
                "symbol": str(row[0]),
                "side": str(row[1]),
                "quantity": int(row[2]),
                "price": float(row[3]),
                "timestamp": str(row[4]),
                "commission": float(row[5]),
                "stamp_duty": float(row[6]),
            }
            for row in rows
        ]

    def save_backtest_run(
        self,
        *,
        created_at: str,
        strategy_name: str,
        symbols: list[str],
        fast_window: int,
        slow_window: int,
        trade_size: int,
        metrics,
        final_equity: float,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO backtest_runs (
                    created_at,
                    strategy_name,
                    symbols,
                    fast_window,
                    slow_window,
                    trade_size,
                    total_return_pct,
                    annualized_return_pct,
                    max_drawdown_pct,
                    win_rate_pct,
                    profit_factor,
                    average_win,
                    average_loss,
                    trade_count,
                    equity_volatility_pct,
                    sharpe_ratio,
                    calmar_ratio,
                    expectancy,
                    final_equity
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    created_at,
                    strategy_name,
                    ",".join(symbols),
                    fast_window,
                    slow_window,
                    trade_size,
                    metrics.total_return_pct,
                    metrics.annualized_return_pct,
                    metrics.max_drawdown_pct,
                    metrics.win_rate_pct,
                    metrics.profit_factor,
                    metrics.average_win,
                    metrics.average_loss,
                    metrics.trade_count,
                    metrics.equity_volatility_pct,
                    metrics.sharpe_ratio,
                    metrics.calmar_ratio,
                    metrics.expectancy,
                    final_equity,
                ),
            )

    def save_broker_snapshot(
        self,
        account: AccountInfo,
        positions: list[PositionInfo],
        orders: list[OrderInfo],
        synced_at: str,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO broker_accounts (synced_at, account_id, broker, cash, total_equity, buying_power, environment)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    synced_at,
                    account.account_id,
                    account.broker,
                    account.cash,
                    account.total_equity,
                    account.buying_power,
                    account.environment,
                ),
            )
            for position in positions:
                conn.execute(
                    """
                    INSERT INTO broker_positions (synced_at, account_id, symbol, quantity, average_cost, market_price, market_value)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        synced_at,
                        account.account_id,
                        position.symbol,
                        position.quantity,
                        position.average_cost,
                        position.market_price,
                        position.market_value,
                    ),
                )
            for order in orders:
                conn.execute(
                    """
                    INSERT INTO broker_orders (
                        synced_at,
                        account_id,
                        symbol,
                        side,
                        quantity,
                        price,
                        status,
                        timestamp,
                        broker_order_id,
                        reason
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        synced_at,
                        account.account_id,
                        order.symbol,
                        order.side,
                        order.quantity,
                        order.price,
                        order.status,
                        order.timestamp.isoformat(),
                        order.broker_order_id,
                        order.reason,
                    ),
                )

    def save_broker_trades(self, account_id: str, trades: list[TradeInfo], synced_at: str) -> None:
        with self._connect() as conn:
            for trade in trades:
                if trade.trade_id:
                    existing = conn.execute(
                        """
                        SELECT 1
                        FROM broker_trades
                        WHERE trade_id = ?
                        LIMIT 1
                        """,
                        (trade.trade_id,),
                    ).fetchone()
                    if existing is not None:
                        continue
                conn.execute(
                    """
                    INSERT INTO broker_trades (
                        synced_at,
                        account_id,
                        symbol,
                        side,
                        quantity,
                        price,
                        timestamp,
                        broker_order_id,
                        trade_id,
                        reason
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        synced_at,
                        account_id,
                        trade.symbol,
                        trade.side,
                        trade.quantity,
                        trade.price,
                        trade.timestamp.isoformat(),
                        trade.broker_order_id,
                        trade.trade_id,
                        trade.reason,
                    ),
                )

    def sync_local_orders_with_broker(
        self,
        *,
        broker_orders: list[OrderInfo],
        broker_trades: list[TradeInfo],
    ) -> dict[str, int]:
        updated_orders = 0
        inserted_fills = 0
        seen_trade_order_ids = {trade.broker_order_id for trade in broker_trades if trade.broker_order_id.strip()}
        traded_quantities: dict[str, int] = {}
        for trade in broker_trades:
            if trade.broker_order_id.strip():
                traded_quantities[trade.broker_order_id] = traded_quantities.get(trade.broker_order_id, 0) + trade.quantity

        for order in broker_orders:
            if order.broker_order_id:
                normalized_status = _normalize_local_order_status(order.status, order.broker_order_id in seen_trade_order_ids)
                traded_quantity = traded_quantities.get(order.broker_order_id, 0)
                if 0 < traded_quantity < order.quantity:
                    normalized_status = "PARTIALLY_FILLED"
                elif traded_quantity >= order.quantity > 0:
                    normalized_status = "FILLED"
                updated_orders += self.update_order_status(
                    broker_order_id=order.broker_order_id,
                    status=normalized_status,
                    reason=order.reason,
                )

        for trade in broker_trades:
            fill = Fill(
                symbol=trade.symbol,
                side=_trade_side_to_enum(trade.side),
                quantity=trade.quantity,
                price=trade.price,
                timestamp=trade.timestamp,
                broker_order_id=trade.broker_order_id,
            )
            if self.save_fill_if_missing(fill, trade_id=trade.trade_id):
                inserted_fills += 1
            if trade.broker_order_id:
                target_status = "FILLED"
                broker_order = next((item for item in broker_orders if item.broker_order_id == trade.broker_order_id), None)
                if broker_order is not None and traded_quantities.get(trade.broker_order_id, 0) < broker_order.quantity:
                    target_status = "PARTIALLY_FILLED"
                updated_orders += self.update_order_status(
                    broker_order_id=trade.broker_order_id,
                    status=target_status,
                    reason=trade.reason,
                )
        return {
            "updated_orders": updated_orders,
            "inserted_fills": inserted_fills,
        }

    def save_broker_sync_bundle(
        self,
        account: AccountInfo,
        positions: list[PositionInfo],
        orders: list[OrderInfo],
        trades: list[TradeInfo],
        synced_at: str,
    ) -> None:
        self.save_broker_snapshot(account, positions, orders, synced_at)
        self.save_broker_trades(account.account_id, trades, synced_at)

    def reconcile_orders_with_broker(
        self,
        account_id: str,
        broker_orders: list[OrderInfo],
        broker_trades: list[TradeInfo],
    ) -> ReconciliationSummary:
        with self._connect() as conn:
            local_rows = conn.execute(
                """
                SELECT status, broker_order_id
                FROM orders
                ORDER BY id DESC
                """
            ).fetchall()

        local_statuses = [str(row[0]) for row in local_rows]
        local_broker_ids = {str(row[1]) for row in local_rows if str(row[1]).strip()}
        broker_order_ids = {item.broker_order_id for item in broker_orders if item.broker_order_id.strip()}
        broker_trade_order_ids = {item.broker_order_id for item in broker_trades if item.broker_order_id.strip()}
        unresolved_local = {status for status in local_statuses if status in {"SUBMITTED", "NEW"}}
        unmatched_broker_orders = broker_order_ids - local_broker_ids
        unmatched_broker_trades = broker_trade_order_ids - local_broker_ids

        return ReconciliationSummary(
            local_submitted_orders=sum(1 for status in local_statuses if status == "SUBMITTED"),
            local_partial_orders=sum(1 for status in local_statuses if status == "PARTIALLY_FILLED"),
            local_filled_orders=sum(1 for status in local_statuses if status == "FILLED"),
            local_canceled_orders=sum(1 for status in local_statuses if status == "CANCELED"),
            local_broker_order_ids=len(local_broker_ids),
            broker_orders=len(broker_orders),
            broker_trades=len(broker_trades),
            missing_broker_order_ids=len(unresolved_local) if unresolved_local else max(0, sum(1 for status in local_statuses if status == "SUBMITTED") - len(local_broker_ids)),
            unmatched_broker_orders=len(unmatched_broker_orders),
            unmatched_broker_trades=len(unmatched_broker_trades),
        )

    def pending_local_orders(self) -> list[dict[str, object]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT symbol, side, quantity, timestamp, price, status, broker_order_id, reason
                FROM orders
                WHERE status IN ('NEW', 'SUBMITTED', 'PARTIALLY_FILLED')
                ORDER BY id DESC
                """
            ).fetchall()
        return [
            {
                "symbol": str(row[0]),
                "side": str(row[1]),
                "quantity": int(row[2]),
                "timestamp": str(row[3]),
                "price": None if row[4] is None else float(row[4]),
                "status": str(row[5]),
                "broker_order_id": str(row[6]),
                "reason": str(row[7]),
            }
            for row in rows
        ]

    def dashboard_summary(self) -> DashboardSummary:
        counts = self.counts()
        with self._connect() as conn:
            latest_snapshot = conn.execute(
                """
                SELECT total_value, cash, drawdown
                FROM snapshots
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()

        if latest_snapshot is None:
            return DashboardSummary(
                orders=counts["orders"],
                fills=counts["fills"],
                events=counts["events"],
                backtest_runs=counts["backtest_runs"],
                synced_accounts=counts["broker_accounts"],
                synced_positions=counts["broker_positions"],
                synced_broker_orders=counts["broker_orders"],
                latest_equity=None,
                latest_cash=None,
                latest_drawdown=None,
            )

        return DashboardSummary(
            orders=counts["orders"],
            fills=counts["fills"],
            events=counts["events"],
            backtest_runs=counts["backtest_runs"],
            synced_accounts=counts["broker_accounts"],
            synced_positions=counts["broker_positions"],
            synced_broker_orders=counts["broker_orders"],
            latest_equity=float(latest_snapshot[0]),
            latest_cash=float(latest_snapshot[1]),
            latest_drawdown=float(latest_snapshot[2]),
        )

    def latest_backtest_runs(self, limit: int = 5) -> list[BacktestRunRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    created_at,
                    strategy_name,
                    symbols,
                    fast_window,
                    slow_window,
                    trade_size,
                    total_return_pct,
                    annualized_return_pct,
                    max_drawdown_pct,
                    win_rate_pct,
                    profit_factor,
                    trade_count,
                    sharpe_ratio,
                    calmar_ratio,
                    expectancy,
                    final_equity
                FROM backtest_runs
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._row_to_backtest_run(row) for row in rows]

    def best_backtest_runs(self, limit: int = 5) -> list[BacktestRunRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    created_at,
                    strategy_name,
                    symbols,
                    fast_window,
                    slow_window,
                    trade_size,
                    total_return_pct,
                    annualized_return_pct,
                    max_drawdown_pct,
                    win_rate_pct,
                    profit_factor,
                    trade_count,
                    sharpe_ratio,
                    calmar_ratio,
                    expectancy,
                    final_equity
                FROM backtest_runs
                ORDER BY total_return_pct DESC, sharpe_ratio DESC, max_drawdown_pct ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._row_to_backtest_run(row) for row in rows]

    def recent_events(self, limit: int = 10) -> list[dict[str, str]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT timestamp, severity, event_type, message
                FROM events
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            {
                "timestamp": str(row[0]),
                "severity": str(row[1]),
                "event_type": str(row[2]),
                "message": str(row[3]),
            }
            for row in rows
        ]

    def symbol_fill_summary(self) -> list[dict[str, float | str | int]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    symbol,
                    COUNT(*) AS fill_count,
                    SUM(quantity) AS total_quantity,
                    SUM(commission + stamp_duty) AS total_fees
                FROM fills
                GROUP BY symbol
                ORDER BY symbol
                """
            ).fetchall()
        return [
            {
                "symbol": str(row[0]),
                "fill_count": int(row[1]),
                "total_quantity": int(row[2]),
                "total_fees": float(row[3]),
            }
            for row in rows
        ]

    def latest_broker_account(self) -> dict[str, str | float] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT synced_at, account_id, broker, cash, total_equity, buying_power, environment
                FROM broker_accounts
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()
        if row is None:
            return None
        return {
            "synced_at": str(row[0]),
            "account_id": str(row[1]),
            "broker": str(row[2]),
            "cash": float(row[3]),
            "total_equity": float(row[4]),
            "buying_power": float(row[5]),
            "environment": str(row[6]),
        }

    def latest_broker_sync_summary(self, account_id: str | None = None) -> BrokerSyncSummary | None:
        with self._connect() as conn:
            latest_row = self._latest_broker_account_row(conn, account_id)
            if latest_row is None:
                return None

            latest_synced_at = str(latest_row[0])
            resolved_account_id = str(latest_row[1])
            previous_synced_at = self._previous_broker_synced_at(conn, resolved_account_id, latest_synced_at)

            current_positions = self._position_snapshot(conn, resolved_account_id, latest_synced_at)
            previous_positions = (
                self._position_snapshot(conn, resolved_account_id, previous_synced_at) if previous_synced_at else {}
            )
            position_added, position_removed, position_changed = self._summarize_position_changes(
                previous_positions,
                current_positions,
            )
            current_order_count = self._broker_order_count(conn, resolved_account_id, latest_synced_at)
            previous_order_count = (
                self._broker_order_count(conn, resolved_account_id, previous_synced_at) if previous_synced_at else None
            )

        cash = float(latest_row[3])
        total_equity = float(latest_row[4])
        buying_power = float(latest_row[5])
        previous_account_row = None
        if previous_synced_at is not None:
            with self._connect() as conn:
                previous_account_row = conn.execute(
                    """
                    SELECT cash, total_equity, buying_power
                    FROM broker_accounts
                    WHERE account_id = ? AND synced_at = ?
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (resolved_account_id, previous_synced_at),
                ).fetchone()

        cash_change = None
        total_equity_change = None
        buying_power_change = None
        if previous_account_row is not None:
            cash_change = cash - float(previous_account_row[0])
            total_equity_change = total_equity - float(previous_account_row[1])
            buying_power_change = buying_power - float(previous_account_row[2])

        return BrokerSyncSummary(
            account_id=resolved_account_id,
            broker=str(latest_row[2]),
            environment=str(latest_row[6]),
            synced_at=latest_synced_at,
            previous_synced_at=previous_synced_at,
            cash=cash,
            total_equity=total_equity,
            buying_power=buying_power,
            cash_change=cash_change,
            total_equity_change=total_equity_change,
            buying_power_change=buying_power_change,
            position_count=len(current_positions),
            position_added=position_added,
            position_removed=position_removed,
            position_changed=position_changed,
            broker_order_count=current_order_count,
            broker_order_change=None if previous_order_count is None else current_order_count - previous_order_count,
        )

    def latest_broker_position_changes(
        self,
        account_id: str | None = None,
        limit: int = 5,
    ) -> list[BrokerPositionChange]:
        with self._connect() as conn:
            latest_row = self._latest_broker_account_row(conn, account_id)
            if latest_row is None:
                return []

            latest_synced_at = str(latest_row[0])
            resolved_account_id = str(latest_row[1])
            previous_synced_at = self._previous_broker_synced_at(conn, resolved_account_id, latest_synced_at)
            if previous_synced_at is None:
                return []

            current_positions = self._position_snapshot(conn, resolved_account_id, latest_synced_at)
            previous_positions = self._position_snapshot(conn, resolved_account_id, previous_synced_at)

        changes: list[BrokerPositionChange] = []
        for symbol in sorted(set(previous_positions) | set(current_positions)):
            previous_quantity, previous_market_value = previous_positions.get(symbol, (0, 0.0))
            current_quantity, current_market_value = current_positions.get(symbol, (0, 0.0))
            quantity_change = current_quantity - previous_quantity
            market_value_change = current_market_value - previous_market_value
            if previous_quantity == current_quantity and abs(market_value_change) < 1e-9:
                continue
            if symbol not in previous_positions:
                status = "ADDED"
            elif symbol not in current_positions:
                status = "REMOVED"
            else:
                status = "UPDATED"
            changes.append(
                BrokerPositionChange(
                    symbol=symbol,
                    status=status,
                    previous_quantity=previous_quantity,
                    current_quantity=current_quantity,
                    quantity_change=quantity_change,
                    previous_market_value=previous_market_value,
                    current_market_value=current_market_value,
                    market_value_change=market_value_change,
                )
            )

        changes.sort(key=lambda item: abs(item.market_value_change), reverse=True)
        return changes[:limit]

    def _latest_broker_account_row(
        self,
        conn: sqlite3.Connection,
        account_id: str | None,
    ) -> tuple[object, ...] | None:
        if account_id is None:
            return conn.execute(
                """
                SELECT synced_at, account_id, broker, cash, total_equity, buying_power, environment
                FROM broker_accounts
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()
        return conn.execute(
            """
            SELECT synced_at, account_id, broker, cash, total_equity, buying_power, environment
            FROM broker_accounts
            WHERE account_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (account_id,),
        ).fetchone()

    def _previous_broker_synced_at(
        self,
        conn: sqlite3.Connection,
        account_id: str,
        latest_synced_at: str,
    ) -> str | None:
        row = conn.execute(
            """
            SELECT synced_at
            FROM broker_accounts
            WHERE account_id = ? AND synced_at <> ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (account_id, latest_synced_at),
        ).fetchone()
        return None if row is None else str(row[0])

    def _position_snapshot(
        self,
        conn: sqlite3.Connection,
        account_id: str,
        synced_at: str,
    ) -> dict[str, tuple[int, float]]:
        rows = conn.execute(
            """
            SELECT symbol, quantity, market_value
            FROM broker_positions
            WHERE account_id = ? AND synced_at = ?
            """,
            (account_id, synced_at),
        ).fetchall()
        return {str(row[0]): (int(row[1]), float(row[2])) for row in rows}

    def _broker_order_count(
        self,
        conn: sqlite3.Connection,
        account_id: str,
        synced_at: str,
    ) -> int:
        row = conn.execute(
            """
            SELECT COUNT(*)
            FROM broker_orders
            WHERE account_id = ? AND synced_at = ?
            """,
            (account_id, synced_at),
        ).fetchone()
        return 0 if row is None else int(row[0])

    def _summarize_position_changes(
        self,
        previous_positions: dict[str, tuple[int, float]],
        current_positions: dict[str, tuple[int, float]],
    ) -> tuple[int, int, int]:
        added = 0
        removed = 0
        changed = 0
        for symbol in set(previous_positions) | set(current_positions):
            if symbol not in previous_positions:
                added += 1
                continue
            if symbol not in current_positions:
                removed += 1
                continue
            previous_quantity, previous_market_value = previous_positions[symbol]
            current_quantity, current_market_value = current_positions[symbol]
            if previous_quantity != current_quantity or abs(current_market_value - previous_market_value) >= 1e-9:
                changed += 1
        return added, removed, changed

    def _row_to_backtest_run(self, row: tuple[object, ...]) -> BacktestRunRecord:
        return BacktestRunRecord(
            created_at=str(row[0]),
            strategy_name=str(row[1]),
            symbols=str(row[2]),
            fast_window=int(row[3]),
            slow_window=int(row[4]),
            trade_size=int(row[5]),
            total_return_pct=float(row[6]),
            annualized_return_pct=float(row[7]),
            max_drawdown_pct=float(row[8]),
            win_rate_pct=float(row[9]),
            profit_factor=float(row[10]),
            trade_count=int(row[11]),
            sharpe_ratio=float(row[12]),
            calmar_ratio=float(row[13]),
            expectancy=float(row[14]),
            final_equity=float(row[15]),
        )


def _trade_side_to_enum(side: str) -> OrderSide:
    normalized = side.upper()
    if normalized == "SELL":
        return OrderSide.SELL
    return OrderSide.BUY


def _normalize_local_order_status(status: str, has_trade: bool) -> str:
    normalized = status.upper()
    if has_trade and normalized not in {"FILLED", "PARTIALLY_FILLED"}:
        return "PARTIALLY_FILLED"
    if normalized in {"CANCELLED", "CANCELED"}:
        return "CANCELED"
    if normalized in {"PART_FILLED", "PARTIALLY_FILLED", "PARTIAL_FILLED"}:
        return "PARTIALLY_FILLED"
    if normalized in {"FILLED", "REJECTED", "SUBMITTED", "NEW"}:
        return normalized
    return "SUBMITTED"
