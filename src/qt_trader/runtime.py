from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from qt_trader.alerts import AlertMessage, AlertNotifier
from qt_trader.broker.base import BrokerGateway
from qt_trader.guardian import RuntimeStateStore, SignalWatchStateStore
from qt_trader.logging_utils import JsonLogger
from qt_trader.models import Bar, Order, OrderStatus, PortfolioSnapshot, RuntimeEvent, Signal
from qt_trader.portfolio import Portfolio
from qt_trader.risk import RiskManager
from qt_trader.storage import SQLiteStorage
from qt_trader.strategy.base import Strategy


@dataclass(slots=True)
class RuntimeResult:
    snapshots: list[PortfolioSnapshot] = field(default_factory=list)
    executed_orders: list[Order] = field(default_factory=list)
    rejected_orders: list[Order] = field(default_factory=list)


@dataclass(slots=True)
class SignalAlertRecord:
    signal: Signal
    timestamp: datetime
    price: float


@dataclass(slots=True)
class SignalWatchResult:
    scanned_bars: int = 0
    latest_timestamp: datetime | None = None
    alerted_signals: list[SignalAlertRecord] = field(default_factory=list)


class PaperTradingRuntime:
    def __init__(
        self,
        strategy: Strategy,
        broker: BrokerGateway,
        portfolio: Portfolio,
        risk_manager: RiskManager,
        storage: SQLiteStorage | None = None,
        persist_snapshots: bool = True,
        sleep_seconds: float = 0.0,
        logger: JsonLogger | None = None,
        alert_notifier: AlertNotifier | None = None,
        max_drawdown_alert_pct: float | None = None,
        rejected_order_alert_threshold: int = 1,
        state_store: RuntimeStateStore | None = None,
    ) -> None:
        self.strategy = strategy
        self.broker = broker
        self.portfolio = portfolio
        self.risk_manager = risk_manager
        self.storage = storage
        self.persist_snapshots = persist_snapshots
        self.sleep_seconds = sleep_seconds
        self.logger = logger
        self.alert_notifier = alert_notifier
        self.max_drawdown_alert_pct = max_drawdown_alert_pct
        self.rejected_order_alert_threshold = rejected_order_alert_threshold
        self.state_store = state_store
        self._rejected_count = 0

    def run(self, bars: list[Bar]) -> RuntimeResult:
        result = RuntimeResult()
        latest_prices: dict[str, float] = {}
        if self.state_store is not None:
            self.state_store.mark_started()
        self._record_event("runtime_started", "INFO", f"Processing {len(bars)} bars")

        for bar in bars:
            latest_prices[bar.symbol] = bar.close
            snapshot = self.portfolio.snapshot(bar.timestamp, latest_prices)

            for signal in self.strategy.on_bar(bar):
                self._record_event(
                    "signal_generated",
                    "INFO",
                    f"{signal.side.value} {signal.quantity} {signal.symbol} reason={signal.reason}",
                    bar.timestamp,
                )
                order = Order(
                    symbol=signal.symbol,
                    side=signal.side,
                    quantity=signal.quantity,
                    timestamp=bar.timestamp,
                    price=bar.close,
                    reason=signal.reason,
                )
                existing_position = snapshot.positions.get(signal.symbol)
                accepted, reason = self.risk_manager.validate_order(order, snapshot, bar.close, existing_position)
                if not accepted:
                    order.status = OrderStatus.REJECTED
                    order.reason = reason
                    result.rejected_orders.append(order)
                    self._rejected_count += 1
                    self._record_event(
                        "order_rejected",
                        "WARNING",
                        f"{order.symbol} {order.side.value} {order.quantity} rejected: {reason}",
                        order.timestamp,
                    )
                    if self.storage is not None:
                        self.storage.save_order(order)
                    self._maybe_alert_on_rejected_orders()
                    continue

                fill = self.broker.submit_order(order, bar.close)
                self.portfolio.apply_fill(fill)
                order.status = OrderStatus.FILLED
                result.executed_orders.append(order)
                self._record_event(
                    "order_filled",
                    "INFO",
                    f"{order.symbol} {order.side.value} {order.quantity} @ {bar.close:.2f}",
                    order.timestamp,
                )

                if self.storage is not None:
                    self.storage.save_order(order)
                    self.storage.save_fill(fill)

            runtime_snapshot = self.portfolio.snapshot(bar.timestamp, latest_prices)
            result.snapshots.append(runtime_snapshot)
            if self.storage is not None and self.persist_snapshots:
                self.storage.save_snapshot(runtime_snapshot)
            self._maybe_alert_on_drawdown(runtime_snapshot)

            if self.sleep_seconds > 0:
                time.sleep(self.sleep_seconds)

        self._record_event("runtime_finished", "INFO", "Runtime completed successfully")
        if self.state_store is not None:
            self.state_store.mark_completed()
        return result

    def _record_event(
        self,
        event_type: str,
        severity: str,
        message: str,
        timestamp: datetime | None = None,
    ) -> None:
        event = RuntimeEvent(
            event_type=event_type,
            timestamp=timestamp or datetime.now(timezone.utc),
            severity=severity,
            message=message,
        )
        if self.storage is not None:
            self.storage.save_event(event)
        if self.logger is not None:
            self.logger.log(
                event_type,
                {
                    "severity": severity,
                    "message": message,
                    "event_timestamp": event.timestamp.isoformat(),
                },
            )

    def _maybe_alert_on_drawdown(self, snapshot: PortfolioSnapshot) -> None:
        if self.alert_notifier is None or self.max_drawdown_alert_pct is None:
            return
        if snapshot.drawdown >= self.max_drawdown_alert_pct:
            self.alert_notifier.send(
                AlertMessage(
                    severity="WARNING",
                    title="Drawdown threshold reached",
                    body=(
                        f"drawdown={snapshot.drawdown:.2%}, "
                        f"equity={snapshot.total_value:.2f}, time={snapshot.timestamp.isoformat()}"
                    ),
                )
            )
            self.max_drawdown_alert_pct = None

    def _maybe_alert_on_rejected_orders(self) -> None:
        if self.alert_notifier is None:
            return
        if self._rejected_count >= self.rejected_order_alert_threshold:
            self.alert_notifier.send(
                AlertMessage(
                    severity="WARNING",
                    title="Rejected order threshold reached",
                    body=f"rejected_orders={self._rejected_count}",
                )
            )
            self.rejected_order_alert_threshold = 10**9


class SignalWatchingRuntime:
    def __init__(
        self,
        strategy: Strategy,
        storage: SQLiteStorage | None = None,
        logger: JsonLogger | None = None,
        alert_notifier: AlertNotifier | None = None,
        signal_state_store: SignalWatchStateStore | None = None,
    ) -> None:
        self.strategy = strategy
        self.storage = storage
        self.logger = logger
        self.alert_notifier = alert_notifier
        self.signal_state_store = signal_state_store

    def scan(self, bars: list[Bar]) -> SignalWatchResult:
        result = SignalWatchResult(scanned_bars=len(bars))
        if not bars:
            self._record_event("signal_scan_empty", "WARNING", "No market data loaded")
            return result

        latest_timestamp = max(bar.timestamp for bar in bars)
        result.latest_timestamp = latest_timestamp
        if self.signal_state_store is not None:
            self.signal_state_store.mark_started()
        self._record_event("signal_scan_started", "INFO", f"Processing {len(bars)} bars")

        for bar in bars:
            signals = self.strategy.on_bar(bar)
            if bar.timestamp != latest_timestamp:
                continue
            for signal in signals:
                signal_key = self._signal_key(signal, bar)
                if self.signal_state_store is not None and self.signal_state_store.has_seen(signal_key):
                    continue
                result.alerted_signals.append(SignalAlertRecord(signal=signal, timestamp=bar.timestamp, price=bar.close))
                self._record_event(
                    "signal_alerted",
                    "INFO",
                    (
                        f"{signal.symbol} {signal.side.value} {signal.quantity} "
                        f"@ {bar.close:.2f} reason={signal.reason}"
                    ),
                    bar.timestamp,
                )
                if self.alert_notifier is not None:
                    self.alert_notifier.send(
                        AlertMessage(
                            severity="INFO",
                            title=f"Signal {signal.side.value}",
                            body=(
                                f"{signal.symbol} qty={signal.quantity} "
                                f"price={bar.close:.2f} time={bar.timestamp.isoformat()} reason={signal.reason}"
                            ),
                        )
                    )
                if self.signal_state_store is not None:
                    self.signal_state_store.mark_seen(signal_key)

        self._record_event(
            "signal_scan_finished",
            "INFO",
            f"latest_bar={latest_timestamp.isoformat()} alerted={len(result.alerted_signals)}",
        )
        if self.signal_state_store is not None:
            self.signal_state_store.mark_completed()
        return result

    def _signal_key(self, signal: Signal, bar: Bar) -> str:
        return "|".join(
            [
                bar.timestamp.isoformat(),
                signal.symbol,
                signal.side.value,
                str(signal.quantity),
                signal.reason,
            ]
        )

    def _record_event(
        self,
        event_type: str,
        severity: str,
        message: str,
        timestamp: datetime | None = None,
    ) -> None:
        event = RuntimeEvent(
            event_type=event_type,
            timestamp=timestamp or datetime.now(timezone.utc),
            severity=severity,
            message=message,
        )
        if self.storage is not None:
            self.storage.save_event(event)
        if self.logger is not None:
            self.logger.log(
                event_type,
                {
                    "severity": severity,
                    "message": message,
                    "event_timestamp": event.timestamp.isoformat(),
                },
            )
