from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Protocol

from qt_trader.broker.terminal_client import TerminalClient
from qt_trader.models import AccountInfo, OrderInfo, PositionInfo


class QMTQueryAdapter(Protocol):
    def get_account_info(self) -> AccountInfo:
        ...

    def get_positions(self) -> list[PositionInfo]:
        ...

    def get_orders(self) -> list[OrderInfo]:
        ...


@dataclass(slots=True)
class QMTSdkClient(TerminalClient):
    broker_name: str
    account_id: str
    terminal_path: str
    environment: str = "qmt_sdk_readonly"
    sdk_module: str = "xtquant"
    session_id: int = 1
    adapter: QMTQueryAdapter | None = None

    def __post_init__(self) -> None:
        if self.adapter is None:
            self.adapter = self._build_adapter()

    def get_account_info(self) -> AccountInfo:
        return self.adapter.get_account_info()

    def get_positions(self) -> list[PositionInfo]:
        return self.adapter.get_positions()

    def get_orders(self) -> list[OrderInfo]:
        return self.adapter.get_orders()

    def _build_adapter(self) -> QMTQueryAdapter:
        try:
            importlib.import_module(self.sdk_module)
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                f"QMT SDK module '{self.sdk_module}' is not installed. "
                "Install the broker SDK or switch broker.terminal_client_mode back to 'mock'."
            ) from exc

        raise RuntimeError(
            "QMT SDK module import succeeded, but concrete query adapter is not wired yet. "
            "Inject a QMTQueryAdapter in tests/dev, or implement the xtquant session adapter next."
        )
