from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from qt_trader.models import Fill, Order, PortfolioSnapshot, RuntimeEvent


@dataclass(slots=True)
class DashboardSummary:
    orders: int
    fills: int
    events: int
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
        return {"orders": orders, "fills": fills, "snapshots": snapshots, "events": events}

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
                latest_equity=None,
                latest_cash=None,
                latest_drawdown=None,
            )

        return DashboardSummary(
            orders=counts["orders"],
            fills=counts["fills"],
            events=counts["events"],
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
