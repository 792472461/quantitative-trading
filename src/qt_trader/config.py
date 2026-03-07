from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator


class BacktestConfig(BaseModel):
    initial_cash: float = Field(default=100000.0, gt=0)
    commission_rate: float = Field(default=0.0003, ge=0)
    min_commission: float = Field(default=5.0, ge=0)
    stamp_duty_rate: float = Field(default=0.001, ge=0)
    slippage_bps: float = Field(default=5.0, ge=0)
    max_position_pct: float = Field(default=0.2, gt=0, le=1)
    max_total_exposure_pct: float = Field(default=0.8, gt=0, le=1)
    max_positions: int = Field(default=10, gt=0)
    max_symbol_quantity: int = Field(default=10000, gt=0)
    max_drawdown_pct: float = Field(default=0.12, gt=0, le=1)


class DataConfig(BaseModel):
    provider: str = "csv"
    csv_path: Path
    csv_paths: dict[str, Path] | None = None
    symbol: str
    symbols: list[str] | None = None
    symbol_column: str = "symbol"
    datetime_column: str = "datetime"
    period: str = "daily"
    start_date: str | None = None
    end_date: str | None = None
    adjust: str = ""
    output_csv_path: Path | None = None

    @field_validator("symbol", mode="before")
    @classmethod
    def normalize_symbol(cls, value: object) -> str:
        return str(value)

    @field_validator("symbols", mode="before")
    @classmethod
    def normalize_symbols(cls, value: object) -> list[str] | None:
        if value is None:
            return None
        if isinstance(value, (list, tuple)):
            return [str(item) for item in value]
        return [str(value)]


class StrategyConfig(BaseModel):
    name: str = "moving_average_cross"
    fast_window: int = Field(default=5, gt=1)
    slow_window: int = Field(default=20, gt=1)
    trade_size: int = Field(default=100, gt=0)


class BrokerConfig(BaseModel):
    provider: str = "paper"
    read_only: bool = False
    api_key_env: str = "BROKER_API_KEY"
    api_secret_env: str = "BROKER_API_SECRET"
    account_id_env: str = "BROKER_ACCOUNT_ID"
    base_url: str | None = None
    terminal_path: Path | None = None
    executable_name: str | None = None
    terminal_type: str | None = None
    terminal_state_file: Path | None = None
    state_file: Path = Path("config/broker_readonly_state.json")
    account_endpoint: str = "/account"
    positions_endpoint: str = "/positions"
    orders_endpoint: str = "/orders"
    timeout_seconds: float = Field(default=10.0, gt=0)


class StorageConfig(BaseModel):
    sqlite_path: Path = Path("trading.db")


class RuntimeConfig(BaseModel):
    polling_interval_seconds: float = Field(default=1.0, gt=0)
    persist_snapshots: bool = True
    max_retries: int = Field(default=2, ge=0)
    lock_path: Path = Path("runtime.lock")
    state_path: Path = Path("runtime_state.json")


class LoggingConfig(BaseModel):
    level: str = "INFO"
    jsonl_path: Path = Path("logs/runtime.jsonl")


class AlertConfig(BaseModel):
    enabled: bool = True
    channels: list[str] = ["stdout"]
    max_drawdown_pct: float = Field(default=0.1, ge=0, le=1)
    rejected_order_threshold: int = Field(default=1, ge=1)


class MarketConfig(BaseModel):
    timezone: str = "Asia/Shanghai"
    weekdays: list[int] = [0, 1, 2, 3, 4]
    morning_start: str = "09:30"
    morning_end: str = "11:30"
    afternoon_start: str = "13:00"
    afternoon_end: str = "15:00"
    holidays: list[str] = []
    makeup_workdays: list[str] = []
    holiday_files: list[Path] = []


class AppConfig(BaseModel):
    environment: str = "paper"
    data: DataConfig
    backtest: BacktestConfig = BacktestConfig()
    strategy: StrategyConfig = StrategyConfig()
    broker: BrokerConfig = BrokerConfig()
    storage: StorageConfig = StorageConfig()
    runtime: RuntimeConfig = RuntimeConfig()
    logging: LoggingConfig = LoggingConfig()
    alert: AlertConfig = AlertConfig()
    market: MarketConfig = MarketConfig()


def load_config(path: str | Path) -> AppConfig:
    file_path = Path(path)
    raw = yaml.safe_load(file_path.read_text(encoding="utf-8"))
    return AppConfig.model_validate(raw)
