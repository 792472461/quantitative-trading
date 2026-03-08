from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from qt_trader.alerts import AlertMessage, AlertNotifier
from qt_trader.broker.base import BrokerGateway
from qt_trader.guardian import RuntimeStateStore, SignalWatchStateStore
from qt_trader.logging_utils import JsonLogger
from qt_trader.models import (
    AccountInfo,
    Bar,
    Order,
    OrderInfo,
    OrderStatus,
    PortfolioSnapshot,
    Position,
    PositionInfo,
    RuntimeEvent,
    Signal,
    TradeInfo,
)
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


@dataclass(slots=True)
class LiveTradingResult:
    scanned_bars: int = 0
    latest_timestamp: datetime | None = None
    submitted_orders: list[OrderInfo] = field(default_factory=list)
    rejected_orders: list[Order] = field(default_factory=list)


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


class LiveTradingRuntime:
    def __init__(
        self,
        strategy: Strategy,
        broker: BrokerGateway,
        risk_manager: RiskManager,
        storage: SQLiteStorage | None = None,
        logger: JsonLogger | None = None,
        alert_notifier: AlertNotifier | None = None,
        signal_state_store: SignalWatchStateStore | None = None,
        state_store: RuntimeStateStore | None = None,
        sync_broker_after_order: bool = True,
    ) -> None:
        self.strategy = strategy
        self.broker = broker
        self.risk_manager = risk_manager
        self.storage = storage
        self.logger = logger
        self.alert_notifier = alert_notifier
        self.signal_state_store = signal_state_store
        self.state_store = state_store
        self.sync_broker_after_order = sync_broker_after_order

    def execute(self, bars: list[Bar]) -> LiveTradingResult:
        result = LiveTradingResult(scanned_bars=len(bars))
        if not bars:
            self._record_event("live_trade_empty", "WARNING", "No market data loaded")
            return result

        latest_timestamp = max(bar.timestamp for bar in bars)
        result.latest_timestamp = latest_timestamp
        if self.state_store is not None:
            self.state_store.mark_started()
        if self.signal_state_store is not None:
            self.signal_state_store.mark_started()
        self._record_event("live_trade_started", "INFO", f"Processing {len(bars)} bars")

        latest_prices = {bar.symbol: bar.close for bar in bars if bar.timestamp == latest_timestamp}
        broker_account = self.broker.get_account_info()
        broker_positions = self.broker.get_positions()
        broker_orders = self.broker.get_orders()
        broker_trades = self.broker.get_trades()
        snapshot = self._snapshot_from_broker(
            account=broker_account,
            positions=broker_positions,
            latest_prices=latest_prices,
            timestamp=latest_timestamp,
        )
        if self.storage is not None:
            self.storage.save_broker_sync_bundle(
                broker_account,
                broker_positions,
                broker_orders,
                broker_trades,
                datetime.now(timezone.utc).isoformat(),
            )
            sync_result = self.storage.sync_local_orders_with_broker(
                broker_orders=broker_orders,
                broker_trades=broker_trades,
            )
            if sync_result["updated_orders"] or sync_result["inserted_fills"]:
                self._record_event(
                    "live_order_sync",
                    "INFO",
                    (
                        f"updated_orders={sync_result['updated_orders']} "
                        f"inserted_fills={sync_result['inserted_fills']}"
                    ),
                )

        try:
            for bar in bars:
                signals = self.strategy.on_bar(bar)
                if bar.timestamp != latest_timestamp:
                    continue
                for signal in signals:
                    signal_key = self._signal_key(signal, bar)
                    if self.signal_state_store is not None and self.signal_state_store.has_seen(signal_key):
                        continue

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
                        self._record_event(
                            "live_order_rejected",
                            "WARNING",
                            f"{order.symbol} {order.side.value} {order.quantity} rejected: {reason}",
                            order.timestamp,
                        )
                        if self.storage is not None:
                            self.storage.save_order(order)
                        continue

                    if not hasattr(self.broker, "place_order"):
                        raise RuntimeError("Configured broker does not support live order placement")
                    broker_order = self.broker.place_order(order, bar.close)
                    order.broker_order_id = broker_order.broker_order_id
                    order.status = OrderStatus.SUBMITTED
                    result.submitted_orders.append(broker_order)
                    if self.storage is not None:
                        self.storage.save_order(order)
                    self._record_event(
                        "live_order_submitted",
                        "INFO",
                        f"{order.symbol} {order.side.value} {order.quantity} submitted",
                        order.timestamp,
                    )
                    if self.alert_notifier is not None:
                        self.alert_notifier.send(
                            AlertMessage(
                                severity="INFO",
                                title=f"Live Order {order.side.value}",
                                body=f"{order.symbol} qty={order.quantity} price={bar.close:.2f}",
                            )
                        )
                    if self.signal_state_store is not None:
                        self.signal_state_store.mark_seen(signal_key)
            if self.sync_broker_after_order and result.submitted_orders and self.storage is not None:
                self._sync_broker_state()
        except Exception as exc:  # noqa: BLE001
            if self.state_store is not None:
                self.state_store.mark_failed(str(exc), 0)
            if self.signal_state_store is not None:
                self.signal_state_store.mark_failed(str(exc))
            self._record_event("live_trade_failed", "ERROR", str(exc))
            raise

        self._record_event(
            "live_trade_finished",
            "INFO",
            f"latest_bar={latest_timestamp.isoformat()} submitted={len(result.submitted_orders)} rejected={len(result.rejected_orders)}",
        )
        if self.state_store is not None:
            self.state_store.mark_completed()
        if self.signal_state_store is not None:
            self.signal_state_store.mark_completed()
        return result

    def _sync_broker_state(self) -> None:
        if self.storage is None:
            return
        account = self.broker.get_account_info()
        positions = self.broker.get_positions()
        orders = self.broker.get_orders()
        trades = self.broker.get_trades()
        self.storage.save_broker_sync_bundle(
            account,
            positions,
            orders,
            trades,
            datetime.now(timezone.utc).isoformat(),
        )
        sync_result = self.storage.sync_local_orders_with_broker(
            broker_orders=orders,
            broker_trades=trades,
        )
        if sync_result["updated_orders"] or sync_result["inserted_fills"]:
            self._record_event(
                "live_order_sync",
                "INFO",
                f"updated_orders={sync_result['updated_orders']} inserted_fills={sync_result['inserted_fills']}",
            )

    def _snapshot_from_broker(
        self,
        account: AccountInfo,
        positions: list[PositionInfo],
        latest_prices: dict[str, float],
        timestamp: datetime,
    ) -> PortfolioSnapshot:
        normalized_positions: dict[str, Position] = {}
        positions_value = 0.0
        for item in positions:
            market_price = latest_prices.get(item.symbol, item.market_price)
            market_value = item.quantity * market_price
            positions_value += market_value
            normalized_positions[item.symbol] = Position(
                symbol=item.symbol,
                quantity=item.quantity,
                average_cost=item.average_cost,
            )
        return PortfolioSnapshot(
            timestamp=timestamp,
            cash=account.cash,
            total_value=account.total_equity,
            positions_value=positions_value,
            drawdown=0.0,
            positions=normalized_positions,
        )

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
