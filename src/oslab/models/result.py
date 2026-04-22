"""Run result models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class RunResult:
    """Serializable run metadata for dry/skeleton runs."""

    run_id: str
    scenario_id: str
    status: str
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: str | None = None
    failure_class: str | None = None
    selected_guest_channel: str | None = None
    reports: dict[str, str] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)

    def complete(self, status: str, *, failure_class: str | None = None) -> None:
        self.status = status
        self.failure_class = failure_class
        self.completed_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "runId": self.run_id,
            "scenarioId": self.scenario_id,
            "status": self.status,
            "startedAt": self.started_at,
            "completedAt": self.completed_at,
            "failureClass": self.failure_class,
            "selectedGuestChannel": self.selected_guest_channel,
            "reports": self.reports,
            "details": self.details,
        }


def make_run_id(scenario_id: str) -> str:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    safe_id = "".join(ch if ch.isalnum() or ch in ("-", "_") else "-" for ch in scenario_id)
    return f"{timestamp}-{safe_id}"


def relative_to_cwd(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(path.resolve())

