from __future__ import annotations

import json
from contextlib import AbstractContextManager
from dataclasses import asdict, dataclass
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
