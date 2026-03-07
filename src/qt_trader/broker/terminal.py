from __future__ import annotations

from pathlib import Path

from qt_trader.broker.base import BrokerGateway
from qt_trader.broker.terminal_client import MockTerminalClient, TerminalClient
from qt_trader.models import Fill, Order


class LocalTerminalReadOnlyBroker(BrokerGateway):
    def __init__(
        self,
        broker_name: str,
        account_id: str,
        terminal_type: str,
        terminal_path: str | Path,
        state_file: str | Path | None = None,
        executable_name: str | None = None,
        environment: str = "readonly_terminal",
        client: TerminalClient | None = None,
    ) -> None:
        if client is None and state_file is None:
            raise ValueError("state_file is required when terminal client is not provided")
        self.broker_name = broker_name
        self.account_id = account_id
        self.terminal_type = terminal_type
        self.terminal_path = Path(terminal_path)
        self.state_file = None if state_file is None else Path(state_file)
        self.executable_name = executable_name
        self.environment = environment
        self.client = client or MockTerminalClient(
            broker_name=broker_name,
            account_id=account_id,
            state_file=Path(state_file),
            environment=environment,
        )

    @property
    def executable_path(self) -> Path | None:
        if not self.executable_name:
            return None
        return self.terminal_path / self.executable_name

    def submit_order(self, order: Order, market_price: float) -> Fill:
        raise RuntimeError(
            f"Broker '{self.broker_name}' is configured as terminal read-only. Real order submission is disabled."
        )

    def get_account_info(self):
        return self.client.get_account_info()

    def get_positions(self):
        return self.client.get_positions()

    def get_orders(self):
        return self.client.get_orders()
