"""Interface abstrata do motor de downloads.

O resto da aplicação só conhece esta interface; o aria2 é uma implementação.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from nova_dm.core.models import AddRequest, EngineStatus


class DownloadEngine(ABC):
    @abstractmethod
    def start(self) -> None:
        """Arranca o motor. Levanta EngineUnavailableError se não for possível."""

    @abstractmethod
    def stop(self) -> None:
        """Pára o motor e liberta todos os recursos (sem processos órfãos)."""

    @property
    @abstractmethod
    def is_running(self) -> bool: ...

    @abstractmethod
    def add(self, request: AddRequest) -> str:
        """Adiciona uma transferência e devolve o identificador do motor (gid)."""

    @abstractmethod
    def pause(self, gid: str) -> None: ...

    @abstractmethod
    def resume(self, gid: str) -> None: ...

    @abstractmethod
    def forget(self, gid: str) -> None:
        """Pára a transferência (se existir) e remove-a da memória do motor.

        Não apaga ficheiros do disco.
        """

    def reorder(self, gids: list[str]) -> None:  # noqa: B027 - opcional: motores sem fila ignoram
        """Define a prioridade das transferências em espera (a primeira é a próxima a arrancar)."""

    @abstractmethod
    def snapshot(self) -> list[EngineStatus]:
        """Estado de todas as transferências conhecidas pelo motor."""

    @abstractmethod
    def set_global_options(self, *, max_concurrent: int | None = None, download_limit: int | None = None) -> None:
        """Altera opções globais (limite de transferências simultâneas e velocidade em bytes/s)."""
