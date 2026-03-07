from __future__ import annotations

from qt_trader.broker.http_readonly import HTTPReadOnlyBroker, HTTPSessionProtocol


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
