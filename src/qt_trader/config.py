from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class BacktestConfig(BaseModel):
    initial_cash: float = Field(default=100000.0, gt=0)
    commission_rate: float = Field(default=0.0003, ge=0)
    max_position_pct: float = Field(default=0.2, gt=0, le=1)
    max_drawdown_pct: float = Field(default=0.12, gt=0, le=1)


class DataConfig(BaseModel):
    csv_path: Path
    symbol: str
    datetime_column: str = "datetime"


class StrategyConfig(BaseModel):
    name: str = "moving_average_cross"
    fast_window: int = Field(default=5, gt=1)
    slow_window: int = Field(default=20, gt=1)
    trade_size: int = Field(default=100, gt=0)


class BrokerConfig(BaseModel):
    provider: str = "paper"
    api_key_env: str = "BROKER_API_KEY"
    api_secret_env: str = "BROKER_API_SECRET"
    account_id_env: str = "BROKER_ACCOUNT_ID"
    base_url: str | None = None


class StorageConfig(BaseModel):
    sqlite_path: Path = Path("trading.db")


class RuntimeConfig(BaseModel):
    polling_interval_seconds: float = Field(default=1.0, gt=0)
    persist_snapshots: bool = True


class AppConfig(BaseModel):
    environment: str = "paper"
    data: DataConfig
    backtest: BacktestConfig = BacktestConfig()
    strategy: StrategyConfig = StrategyConfig()
    broker: BrokerConfig = BrokerConfig()
    storage: StorageConfig = StorageConfig()
    runtime: RuntimeConfig = RuntimeConfig()


def load_config(path: str | Path) -> AppConfig:
    file_path = Path(path)
    raw = yaml.safe_load(file_path.read_text(encoding="utf-8"))
    return AppConfig.model_validate(raw)
