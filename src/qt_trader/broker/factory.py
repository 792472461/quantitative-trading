from __future__ import annotations

import os

from qt_trader.broker.base import BrokerGateway
from qt_trader.broker.guojin import GuojinHTTPReadOnlyBroker, GuojinPtradeBroker, GuojinQMTBroker
from qt_trader.broker.http_readonly import HTTPReadOnlyBroker
from qt_trader.broker.paper import PaperBroker
from qt_trader.broker.qmt_sdk import QMTSdkClient
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

    if provider == "http_readonly":
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
        if not config.broker.base_url:
            raise BrokerConfigurationError("Broker provider 'http_readonly' requires broker.base_url")
        return HTTPReadOnlyBroker(
            broker_name="http_readonly",
            account_id=os.getenv(config.broker.account_id_env, "http-readonly-account"),
            base_url=config.broker.base_url,
            account_endpoint=config.broker.account_endpoint,
            positions_endpoint=config.broker.positions_endpoint,
            orders_endpoint=config.broker.orders_endpoint,
            api_key=os.getenv(config.broker.api_key_env, ""),
            api_secret=os.getenv(config.broker.api_secret_env, ""),
            timeout_seconds=config.broker.timeout_seconds,
        )

    if provider == "guojin_http_readonly":
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
        if not config.broker.base_url:
            raise BrokerConfigurationError("Broker provider 'guojin_http_readonly' requires broker.base_url")
        return GuojinHTTPReadOnlyBroker(
            account_id=os.getenv(config.broker.account_id_env, "guojin-readonly-account"),
            base_url=config.broker.base_url,
            account_endpoint=config.broker.account_endpoint,
            positions_endpoint=config.broker.positions_endpoint,
            orders_endpoint=config.broker.orders_endpoint,
            api_key=os.getenv(config.broker.api_key_env, ""),
            api_secret=os.getenv(config.broker.api_secret_env, ""),
            timeout_seconds=config.broker.timeout_seconds,
        )

    if provider in {"guojin_qmt", "guojin_ptrade"}:
        missing = [env_name for env_name in (config.broker.account_id_env,) if not os.getenv(env_name)]
        if missing:
            raise BrokerConfigurationError(
                f"Broker provider '{config.broker.provider}' requires env vars: {', '.join(missing)}"
            )
        if config.broker.terminal_path is None:
            raise BrokerConfigurationError(
                f"Broker provider '{config.broker.provider}' requires broker.terminal_path"
            )
        client_mode = config.broker.terminal_client_mode.lower()
        if provider == "guojin_qmt" and client_mode == "qmt_sdk":
            try:
                client = QMTSdkClient(
                    broker_name="guojin_qmt",
                    account_id=os.getenv(config.broker.account_id_env, "guojin-qmt-account"),
                    terminal_path=str(config.broker.terminal_path),
                    environment="qmt_sdk_readonly",
                    sdk_module=config.broker.sdk_module or "xtquant",
                    session_id=config.broker.qmt_session_id,
                )
            except RuntimeError as exc:
                raise BrokerConfigurationError(str(exc)) from exc
            return GuojinQMTBroker(
                account_id=os.getenv(config.broker.account_id_env, "guojin-qmt-account"),
                terminal_path=config.broker.terminal_path,
                executable_name=config.broker.executable_name or "XtMiniQmt.exe",
                client=client,
            )
        if config.broker.terminal_state_file is None:
            raise BrokerConfigurationError(
                f"Broker provider '{config.broker.provider}' requires broker.terminal_state_file"
            )
        if provider == "guojin_qmt":
            return GuojinQMTBroker(
                account_id=os.getenv(config.broker.account_id_env, "guojin-qmt-account"),
                terminal_path=config.broker.terminal_path,
                state_file=config.broker.terminal_state_file,
                executable_name=config.broker.executable_name or "XtMiniQmt.exe",
            )
        return GuojinPtradeBroker(
            account_id=os.getenv(config.broker.account_id_env, "guojin-ptrade-account"),
            terminal_path=config.broker.terminal_path,
            state_file=config.broker.terminal_state_file,
            executable_name=config.broker.executable_name or "PtradeClient.exe",
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
