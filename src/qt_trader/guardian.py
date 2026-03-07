from __future__ import annotations

import json
from contextlib import AbstractContextManager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path


class RuntimeLockError(RuntimeError):
    pass


class RuntimeLock(AbstractContextManager["RuntimeLock"]):
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def __enter__(self) -> "RuntimeLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            raise RuntimeLockError(f"Runtime lock already exists: {self.path}")
        self.path.write_text(
            json.dumps({"locked_at": datetime.now(timezone.utc).isoformat()}),
            encoding="utf-8",
        )
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.path.exists():
            self.path.unlink()
        return False


@dataclass(slots=True)
class RuntimeState:
    last_run_started_at: str | None = None
    last_run_completed_at: str | None = None
    last_status: str = "idle"
    last_error: str | None = None
    retry_count: int = 0


@dataclass(slots=True)
class SignalWatchState:
    last_scan_started_at: str | None = None
    last_scan_completed_at: str | None = None
    last_status: str = "idle"
    last_error: str | None = None
    seen_signal_keys: list[str] = field(default_factory=list)


@dataclass(slots=True)
class DailyWorkflowState:
    last_status: str = "idle"
    last_error: str | None = None
    last_pre_market_date: str | None = None
    last_post_close_date: str | None = None
    last_run_started_at: str | None = None
    last_run_completed_at: str | None = None


class RuntimeStateStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> RuntimeState:
        if not self.path.exists():
            return RuntimeState()
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        return RuntimeState(**raw)

    def save(self, state: RuntimeState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(asdict(state), ensure_ascii=True, indent=2), encoding="utf-8")

    def mark_started(self) -> RuntimeState:
        state = self.load()
        state.last_run_started_at = datetime.now(timezone.utc).isoformat()
        state.last_status = "running"
        state.last_error = None
        self.save(state)
        return state

    def mark_failed(self, error: str, retry_count: int) -> RuntimeState:
        state = self.load()
        state.last_status = "failed"
        state.last_error = error
        state.retry_count = retry_count
        self.save(state)
        return state

    def mark_completed(self) -> RuntimeState:
        state = self.load()
        state.last_run_completed_at = datetime.now(timezone.utc).isoformat()
        state.last_status = "completed"
        state.last_error = None
        state.retry_count = 0
        self.save(state)
        return state


class SignalWatchStateStore:
    def __init__(self, path: str | Path, max_seen_signals: int = 500) -> None:
        self.path = Path(path)
        self.max_seen_signals = max_seen_signals

    def load(self) -> SignalWatchState:
        if not self.path.exists():
            return SignalWatchState()
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        return SignalWatchState(**raw)

    def save(self, state: SignalWatchState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(asdict(state), ensure_ascii=True, indent=2), encoding="utf-8")

    def mark_started(self) -> SignalWatchState:
        state = self.load()
        state.last_scan_started_at = datetime.now(timezone.utc).isoformat()
        state.last_status = "running"
        state.last_error = None
        self.save(state)
        return state

    def mark_completed(self) -> SignalWatchState:
        state = self.load()
        state.last_scan_completed_at = datetime.now(timezone.utc).isoformat()
        state.last_status = "completed"
        state.last_error = None
        self.save(state)
        return state

    def mark_failed(self, error: str) -> SignalWatchState:
        state = self.load()
        state.last_status = "failed"
        state.last_error = error
        self.save(state)
        return state

    def has_seen(self, key: str) -> bool:
        return key in self.load().seen_signal_keys

    def mark_seen(self, key: str) -> SignalWatchState:
        state = self.load()
        keys = [item for item in state.seen_signal_keys if item != key]
        keys.append(key)
        state.seen_signal_keys = keys[-self.max_seen_signals :]
        self.save(state)
        return state


class DailyWorkflowStateStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> DailyWorkflowState:
        if not self.path.exists():
            return DailyWorkflowState()
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        return DailyWorkflowState(**raw)

    def save(self, state: DailyWorkflowState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(asdict(state), ensure_ascii=True, indent=2), encoding="utf-8")

    def mark_started(self) -> DailyWorkflowState:
        state = self.load()
        state.last_status = "running"
        state.last_error = None
        state.last_run_started_at = datetime.now(timezone.utc).isoformat()
        self.save(state)
        return state

    def mark_completed(self) -> DailyWorkflowState:
        state = self.load()
        state.last_status = "completed"
        state.last_error = None
        state.last_run_completed_at = datetime.now(timezone.utc).isoformat()
        self.save(state)
        return state

    def mark_failed(self, error: str) -> DailyWorkflowState:
        state = self.load()
        state.last_status = "failed"
        state.last_error = error
        state.last_run_completed_at = datetime.now(timezone.utc).isoformat()
        self.save(state)
        return state

    def mark_pre_market_done(self, trading_date: str) -> DailyWorkflowState:
        state = self.load()
        state.last_pre_market_date = trading_date
        self.save(state)
        return state

    def mark_post_close_done(self, trading_date: str) -> DailyWorkflowState:
        state = self.load()
        state.last_post_close_date = trading_date
        self.save(state)
        return state
