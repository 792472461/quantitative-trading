from __future__ import annotations

import sqlite3
from pathlib import Path

from qt_trader.models import Fill, Order, PortfolioSnapshot, RuntimeEvent


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
                    commission REAL NOT NULL
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
                INSERT INTO fills (symbol, side, quantity, price, timestamp, commission)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    fill.symbol,
                    fill.side.value,
                    fill.quantity,
                    fill.price,
                    fill.timestamp.isoformat(),
                    fill.commission,
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
