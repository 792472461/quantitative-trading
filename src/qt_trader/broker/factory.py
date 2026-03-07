from __future__ import annotations

import os

from qt_trader.broker.base import BrokerGateway
from qt_trader.broker.paper import PaperBroker
from qt_trader.config import AppConfig


class BrokerConfigurationError(RuntimeError):
    pass


def create_broker(config: AppConfig) -> BrokerGateway:
    provider = config.broker.provider.lower()
    if provider == "paper":
        return PaperBroker(commission_rate=config.backtest.commission_rate)

    missing = [
        env_name
        for env_name in (
            config.broker.api_key_env,
            config.broker.api_secret_env,
            config.broker.account_id_env,
        )
        if not os.getenv(env_name)
    ]
    if missing:
        raise BrokerConfigurationError(
            f"Broker provider '{config.broker.provider}' requires env vars: {', '.join(missing)}"
        )

    raise BrokerConfigurationError(
        f"Broker provider '{config.broker.provider}' is not implemented yet. "
        "Keep provider=paper for now, or add a concrete broker adapter under src/qt_trader/broker/."
    )
