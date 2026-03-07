from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from qt_trader.config import AlertConfig


@dataclass(slots=True)
class AlertMessage:
    severity: str
    title: str
    body: str


class AlertNotifier:
    def __init__(self, config: AlertConfig, output_path: str | Path = "logs/alerts.log") -> None:
        self.config = config
        self.output_path = Path(output_path)
        if "file" in self.config.channels:
            self.output_path.parent.mkdir(parents=True, exist_ok=True)

    def send(self, message: AlertMessage) -> None:
        if not self.config.enabled:
            return

        formatted = f"[{message.severity}] {message.title}: {message.body}"
        if "stdout" in self.config.channels:
            print(formatted)
        if "file" in self.config.channels:
            with self.output_path.open("a", encoding="utf-8") as handle:
                handle.write(formatted + "\n")
