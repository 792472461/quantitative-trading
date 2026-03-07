from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from qt_trader.models import AccountInfo, Fill, Order, OrderInfo, PortfolioSnapshot, PositionInfo, RuntimeEvent


@dataclass(slots=True)
class DashboardSummary:
    orders: int
    fills: int
    events: int
    synced_accounts: int
    synced_positions: int
    synced_broker_orders: int
    latest_equity: float | None
    latest_cash: float | None
    latest_drawdown: float | None


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
                    commission REAL NOT NULL,
                    stamp_duty REAL NOT NULL,
                    slippage_cost REAL NOT NULL
                )
                """
            )
            self._ensure_fill_columns(conn)
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
                    reason TEXT NOT NULL
                )
                """
            )

    def _ensure_fill_columns(self, conn: sqlite3.Connection) -> None:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(fills)").fetchall()}
        if "stamp_duty" not in columns:
            conn.execute("ALTER TABLE fills ADD COLUMN stamp_duty REAL NOT NULL DEFAULT 0")
        if "slippage_cost" not in columns:
            conn.execute("ALTER TABLE fills ADD COLUMN slippage_cost REAL NOT NULL DEFAULT 0")

    def save_order(self, order: Order) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO orders (symbol, side, quantity, timestamp, price, status, reason)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    order.symbol,
                    order.side.value,
                    order.quantity,
                    order.timestamp.isoformat(),
                    order.price,
                    order.status.value,
                    order.reason,
                ),
            )

    def save_fill(self, fill: Fill) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO fills (symbol, side, quantity, price, timestamp, commission, stamp_duty, slippage_cost)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fill.symbol,
                    fill.side.value,
                    fill.quantity,
                    fill.price,
                    fill.timestamp.isoformat(),
                    fill.commission,
                    fill.stamp_duty,
                    fill.slippage_cost,
                ),
            )

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
            broker_accounts = conn.execute("SELECT COUNT(*) FROM broker_accounts").fetchone()[0]
            broker_positions = conn.execute("SELECT COUNT(*) FROM broker_positions").fetchone()[0]
            broker_orders = conn.execute("SELECT COUNT(*) FROM broker_orders").fetchone()[0]
        return {
            "orders": orders,
            "fills": fills,
            "snapshots": snapshots,
            "events": events,
            "broker_accounts": broker_accounts,
            "broker_positions": broker_positions,
            "broker_orders": broker_orders,
        }

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
                    INSERT INTO broker_orders (synced_at, account_id, symbol, side, quantity, price, status, timestamp, reason)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        order.reason,
                    ),
                )

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
            synced_accounts=counts["broker_accounts"],
            synced_positions=counts["broker_positions"],
            synced_broker_orders=counts["broker_orders"],
            latest_equity=float(latest_snapshot[0]),
            latest_cash=float(latest_snapshot[1]),
            latest_drawdown=float(latest_snapshot[2]),
        )

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
