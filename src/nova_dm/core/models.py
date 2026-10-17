"""Modelos de domínio partilhados entre motor, base de dados e interface."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


class DownloadStatus(StrEnum):
    QUEUED = "queued"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def is_finished(self) -> bool:
        return self in (DownloadStatus.COMPLETED, DownloadStatus.FAILED, DownloadStatus.CANCELLED)

    @property
    def is_pending(self) -> bool:
        """Estados em que a transferência ainda deve existir no motor."""
        return self in (DownloadStatus.QUEUED, DownloadStatus.ACTIVE, DownloadStatus.PAUSED)


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass(slots=True)
class DownloadRecord:
    """Uma transferência, tal como é guardada na base de dados."""

    url: str
    filename: str
    directory: str
    id: int | None = None
    status: DownloadStatus = DownloadStatus.QUEUED
    total_bytes: int = 0
    completed_bytes: int = 0
    download_speed: int = 0
    connections: int = 0
    speed_limit: int = 0  # bytes/s; 0 = sem limite
    gid: str | None = None
    category: str = "other"
    error_message: str = ""
    created_at: str = field(default_factory=utc_now_iso)
    completed_at: str | None = None
    position: int = 0  # ordem escolhida pelo utilizador (1 = primeiro); define a prioridade na fila

    @property
    def progress(self) -> float:
        """Fração concluída entre 0.0 e 1.0 (0.0 se o tamanho for desconhecido)."""
        if self.status is DownloadStatus.COMPLETED:
            return 1.0
        if self.total_bytes <= 0:
            return 0.0
        return min(1.0, self.completed_bytes / self.total_bytes)

    @property
    def eta_seconds(self) -> int | None:
        if self.status is not DownloadStatus.ACTIVE or self.download_speed <= 0 or self.total_bytes <= 0:
            return None
        remaining = max(0, self.total_bytes - self.completed_bytes)
        return remaining // self.download_speed

    @property
    def path(self) -> str:
        return f"{self.directory.rstrip('/')}/{self.filename}"


@dataclass(frozen=True, slots=True)
class RequestContext:
    """Contexto HTTP enviado pelo navegador. Só vive em memória: nunca é gravado nem registado."""

    referer: str = ""
    user_agent: str = ""
    cookies: str = field(default="", repr=False)


@dataclass(frozen=True, slots=True)
class AddRequest:
    """Pedido de nova transferência enviado ao motor."""

    url: str
    directory: str
    filename: str
    connections: int = 4
    speed_limit: int = 0
    paused: bool = False
    context: RequestContext | None = None


@dataclass(frozen=True, slots=True)
class EngineStatus:
    """Estado de uma transferência segundo o motor."""

    gid: str
    state: str  # active | waiting | paused | error | complete | removed
    total_bytes: int = 0
    completed_bytes: int = 0
    download_speed: int = 0
    connections: int = 0
    error_code: int = 0
    error_message: str = ""
    path: str = ""
