from __future__ import annotations

import os

from qt_trader.broker.base import BrokerGateway
from qt_trader.broker.paper import PaperBroker
from qt_trader.broker.readonly import ReadOnlyBroker
from qt_trader.config import AppConfig
from qt_trader.costs import ExecutionCostModel
from qt_trader.portfolio import Portfolio


class BrokerConfigurationError(RuntimeError):
    pass


def create_broker(config: AppConfig, portfolio: Portfolio | None = None) -> BrokerGateway:
    provider = config.broker.provider.lower()
    if provider == "paper":
        return PaperBroker(
            cost_model=ExecutionCostModel(
                commission_rate=config.backtest.commission_rate,
                min_commission=config.backtest.min_commission,
                stamp_duty_rate=config.backtest.stamp_duty_rate,
                slippage_bps=config.backtest.slippage_bps,
            ),
            portfolio=portfolio,
        )

    if provider == "readonly":
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
        return ReadOnlyBroker(
            broker_name="readonly",
            account_id=os.getenv(config.broker.account_id_env, "readonly-account"),
            state_file=config.broker.state_file,
            environment="readonly",
        )

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
