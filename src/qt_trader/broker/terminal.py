from __future__ import annotations

from pathlib import Path

from qt_trader.broker.readonly import ReadOnlyBroker


class LocalTerminalReadOnlyBroker(ReadOnlyBroker):
    def __init__(
        self,
        broker_name: str,
        account_id: str,
        terminal_type: str,
        terminal_path: str | Path,
        state_file: str | Path,
        executable_name: str | None = None,
        environment: str = "readonly_terminal",
    ) -> None:
        super().__init__(
            broker_name=broker_name,
            account_id=account_id,
            state_file=state_file,
            environment=environment,
        )
        self.terminal_type = terminal_type
        self.terminal_path = Path(terminal_path)
        self.executable_name = executable_name

    @property
    def executable_path(self) -> Path | None:
        if not self.executable_name:
            return None
        return self.terminal_path / self.executable_name
