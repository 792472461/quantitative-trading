from __future__ import annotations

import importlib
import os
from dataclasses import dataclass
from pathlib import Path

from qt_trader.config import AppConfig
from qt_trader.data.factory import create_data_feed


@dataclass(slots=True)
class PreflightCheck:
    name: str
    status: str
    message: str


def run_preflight_checks(config: AppConfig) -> list[PreflightCheck]:
    checks: list[PreflightCheck] = []
    checks.append(_check_strategy(config))
    checks.append(_check_data_feed(config))
    checks.append(_check_storage_and_logging(config))
    checks.append(_check_market_calendar(config))
    checks.append(_check_alerting(config))
    checks.append(_check_broker_configuration(config))
    return checks


def _check_strategy(config: AppConfig) -> PreflightCheck:
    if config.strategy.name == "moving_average_cross" and config.strategy.fast_window >= config.strategy.slow_window:
        return PreflightCheck("strategy", "FAIL", "fast_window must be smaller than slow_window")
    if config.strategy.name == "auto_rotation":
        benchmark_symbol = config.strategy.benchmark_symbol
        universe = [symbol for symbol in (config.data.symbols or [config.data.symbol]) if symbol != benchmark_symbol]
        if config.strategy.selection_top_n > len(universe):
            return PreflightCheck("strategy", "FAIL", "selection_top_n cannot exceed symbol universe size")
        if config.strategy.min_holding_days < 1 and config.backtest.t_plus_one_sell:
            return PreflightCheck("strategy", "WARN", "t+1 sell is enabled, actual holding period will still be at least 1 day")
    if config.strategy.market_filter_enabled and not config.strategy.benchmark_symbol:
        return PreflightCheck("strategy", "FAIL", "benchmark_symbol is required when market_filter_enabled=true")
    if config.strategy.market_fast_window >= config.strategy.market_slow_window:
        return PreflightCheck("strategy", "FAIL", "market_fast_window must be smaller than market_slow_window")
    return PreflightCheck(
        "strategy",
        "PASS",
        (
            f"{config.strategy.name} fast={config.strategy.fast_window} slow={config.strategy.slow_window} "
            f"market_filter={config.strategy.market_filter_enabled}"
        ),
    )


def _check_data_feed(config: AppConfig) -> PreflightCheck:
    try:
        bars = create_data_feed(config).load()
    except Exception as exc:  # noqa: BLE001
        return PreflightCheck("data_feed", "FAIL", f"unable to load bars: {exc}")

    if not bars:
        return PreflightCheck("data_feed", "FAIL", "no bars returned by data provider")
    symbols = sorted({bar.symbol for bar in bars})
    return PreflightCheck("data_feed", "PASS", f"loaded {len(bars)} bars across {len(symbols)} symbol(s)")


def _check_storage_and_logging(config: AppConfig) -> PreflightCheck:
    paths = [
        Path(config.storage.sqlite_path),
        Path(config.logging.jsonl_path),
        Path(config.runtime.lock_path),
        Path(config.runtime.state_path),
    ]
    for path in paths:
        parent = path.parent if path.parent != Path("") else Path(".")
        try:
            parent.mkdir(parents=True, exist_ok=True)
            probe = parent / ".qt_trader_write_probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
        except Exception as exc:  # noqa: BLE001
            return PreflightCheck("filesystem", "FAIL", f"path not writable: {parent} ({exc})")
    return PreflightCheck("filesystem", "PASS", "storage, runtime, and logging paths are writable")


def _check_market_calendar(config: AppConfig) -> PreflightCheck:
    missing_files = [str(path) for path in config.market.holiday_files if not Path(path).exists()]
    if missing_files:
        return PreflightCheck("market_calendar", "FAIL", f"missing holiday files: {', '.join(missing_files)}")
    if not config.market.holiday_files:
        return PreflightCheck("market_calendar", "WARN", "no holiday override files configured")
    return PreflightCheck("market_calendar", "PASS", f"loaded {len(config.market.holiday_files)} holiday file(s)")


def _check_alerting(config: AppConfig) -> PreflightCheck:
    if not config.alert.enabled:
        return PreflightCheck("alerts", "FAIL", "alerts are disabled")
    if not config.alert.channels:
        return PreflightCheck("alerts", "FAIL", "no alert channels configured")
    return PreflightCheck("alerts", "PASS", f"channels={','.join(config.alert.channels)}")


def _check_broker_configuration(config: AppConfig) -> PreflightCheck:
    provider = config.broker.provider.lower()
    if provider == "paper":
        return PreflightCheck("broker", "WARN", "provider=paper, safe for rehearsal but not live-ready")

    if provider in {"guojin_qmt", "guojin_ptrade", "guojin_qmt_live"}:
        if not os.getenv(config.broker.account_id_env):
            return PreflightCheck("broker", "FAIL", f"missing env vars: {config.broker.account_id_env}")
        if config.broker.terminal_path is None:
            return PreflightCheck("broker", "FAIL", "terminal broker requires broker.terminal_path")
        terminal_path = Path(config.broker.terminal_path)
        if not terminal_path.exists():
            return PreflightCheck("broker", "FAIL", f"terminal path not found: {terminal_path}")
        if config.broker.executable_name:
            executable_path = terminal_path / config.broker.executable_name
            if not executable_path.exists():
                return PreflightCheck("broker", "WARN", f"terminal executable not found: {executable_path}")
        client_mode = config.broker.terminal_client_mode.lower()
        if provider in {"guojin_qmt", "guojin_qmt_live"} and client_mode == "qmt_sdk":
            userdata_path = (
                Path(config.broker.terminal_userdata_path)
                if config.broker.terminal_userdata_path is not None
                else terminal_path / "userdata_mini"
            )
            if not userdata_path.exists():
                return PreflightCheck("broker", "WARN", f"qmt userdata path not found yet: {userdata_path}")
            sdk_module = config.broker.sdk_module or "xtquant"
            try:
                importlib.import_module(sdk_module)
            except ModuleNotFoundError:
                return PreflightCheck("broker", "FAIL", f"qmt sdk module not installed: {sdk_module}")
            if provider == "guojin_qmt_live" and not config.broker.allow_live_trading:
                return PreflightCheck(
                    "broker",
                    "WARN",
                    f"provider={config.broker.provider} sdk ready but live trading switch is disabled",
                )
            return PreflightCheck(
                "broker",
                "PASS" if provider == "guojin_qmt_live" else "WARN",
                (
                    f"provider={config.broker.provider} sdk module ready ({sdk_module}), "
                    f"{'live order path enabled' if provider == 'guojin_qmt_live' else 'query path ready'}"
                ),
            )
        if config.broker.terminal_state_file is None:
            return PreflightCheck("broker", "FAIL", "terminal broker requires broker.terminal_state_file")
        state_file = Path(config.broker.terminal_state_file)
        if not state_file.exists():
            return PreflightCheck("broker", "WARN", f"terminal snapshot file not found yet: {state_file}")
        return PreflightCheck("broker", "WARN", f"provider={config.broker.provider} scaffold ready, trading disabled")

    missing_env = [
        env_name
        for env_name in (
            config.broker.api_key_env,
            config.broker.api_secret_env,
            config.broker.account_id_env,
        )
        if not os.getenv(env_name)
    ]
    if missing_env:
        return PreflightCheck("broker", "FAIL", f"missing env vars: {', '.join(missing_env)}")

    if "readonly" in provider or config.broker.read_only:
        return PreflightCheck("broker", "WARN", f"provider={config.broker.provider} is read-only")

    if not config.broker.base_url:
        return PreflightCheck("broker", "FAIL", "live broker requires broker.base_url")

    return PreflightCheck("broker", "PASS", f"provider={config.broker.provider}")
