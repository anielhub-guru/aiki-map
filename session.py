"""Track one agent work session without modifying its repository."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from threading import Lock


class SessionPhase(str, Enum):
    STARTED = "started"
    ACTIVE = "active"
    STOPPED = "stopped"
    DISMISSED = "dismissed"


@dataclass(frozen=True)
class SessionSnapshot:
    phase: SessionPhase
    repository: str
    source: str
    started_at: str
    stopped_at: str | None
    stop_reason: str | None
    exit_code: int | None

    def as_dict(self) -> dict[str, str | int | None]:
        return {
            "phase": self.phase.value,
            "repository": self.repository,
            "source": self.source,
            "startedAt": self.started_at,
            "stoppedAt": self.stopped_at,
            "stopReason": self.stop_reason,
            "exitCode": self.exit_code,
        }


class SessionState:
    """Provide thread-safe, monotonic session lifecycle updates."""

    def __init__(self, repository: Path, source: str) -> None:
        self.repository = repository.resolve()
        self.source = source
        self._phase = SessionPhase.STARTED
        self._started_at = _now()
        self._stopped_at: str | None = None
        self._stop_reason: str | None = None
        self._exit_code: int | None = None
        self._lock = Lock()

    def mark_active(self) -> None:
        with self._lock:
            if self._phase == SessionPhase.STARTED:
                self._phase = SessionPhase.ACTIVE

    def mark_stopped(self, reason: str, exit_code: int | None = None) -> None:
        with self._lock:
            if self._phase in {SessionPhase.STOPPED, SessionPhase.DISMISSED}:
                return
            self._phase = SessionPhase.STOPPED
            self._stopped_at = _now()
            self._stop_reason = reason
            self._exit_code = exit_code

    def dismiss(self) -> None:
        with self._lock:
            if self._phase in {SessionPhase.STARTED, SessionPhase.ACTIVE}:
                self._phase = SessionPhase.DISMISSED

    def snapshot(self) -> SessionSnapshot:
        with self._lock:
            return SessionSnapshot(
                phase=self._phase,
                repository=str(self.repository),
                source=self.source,
                started_at=self._started_at,
                stopped_at=self._stopped_at,
                stop_reason=self._stop_reason,
                exit_code=self._exit_code,
            )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
