from __future__ import annotations

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
    return PreflightCheck(
        "strategy",
        "PASS",
        f"{config.strategy.name} fast={config.strategy.fast_window} slow={config.strategy.slow_window}",
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

    if provider in {"guojin_qmt", "guojin_ptrade"}:
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
