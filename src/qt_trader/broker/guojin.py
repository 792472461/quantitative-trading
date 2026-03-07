from __future__ import annotations

from pathlib import Path

from qt_trader.broker.http_readonly import HTTPReadOnlyBroker, HTTPSessionProtocol
from qt_trader.broker.terminal import LocalTerminalReadOnlyBroker


class GuojinHTTPReadOnlyBroker(HTTPReadOnlyBroker):
    def __init__(
        self,
        account_id: str,
        base_url: str,
        api_key: str,
        api_secret: str,
        account_endpoint: str = "/account",
        positions_endpoint: str = "/positions",
        orders_endpoint: str = "/orders",
        timeout_seconds: float = 10.0,
        session: HTTPSessionProtocol | None = None,
    ) -> None:
        super().__init__(
            broker_name="guojin_http_readonly",
            account_id=account_id,
            base_url=base_url,
            account_endpoint=account_endpoint,
            positions_endpoint=positions_endpoint,
            orders_endpoint=orders_endpoint,
            api_key=api_key,
            api_secret=api_secret,
            timeout_seconds=timeout_seconds,
            session=session,
        )


class GuojinQMTBroker(LocalTerminalReadOnlyBroker):
    def __init__(
        self,
        account_id: str,
        terminal_path: str | Path,
        state_file: str | Path,
        executable_name: str = "XtMiniQmt.exe",
    ) -> None:
        super().__init__(
            broker_name="guojin_qmt",
            account_id=account_id,
            terminal_type="qmt",
            terminal_path=terminal_path,
            state_file=state_file,
            executable_name=executable_name,
            environment="qmt_readonly",
        )


class GuojinPtradeBroker(LocalTerminalReadOnlyBroker):
    def __init__(
        self,
        account_id: str,
        terminal_path: str | Path,
        state_file: str | Path,
        executable_name: str = "PtradeClient.exe",
    ) -> None:
        super().__init__(
            broker_name="guojin_ptrade",
            account_id=account_id,
            terminal_type="ptrade",
            terminal_path=terminal_path,
            state_file=state_file,
            executable_name=executable_name,
            environment="ptrade_readonly",
        )
