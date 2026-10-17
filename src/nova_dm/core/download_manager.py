"""Gestão do ciclo de vida das transferências.

Junta o motor (aria2) e a base de dados. Não depende de Qt e **não é thread-safe**:
deve ser usado sempre a partir da mesma thread (na aplicação, a thread do motor).

Semântica das ações:
- pausar:   o motor pára a transferência e os dados parciais ficam no disco;
- cancelar: a transferência termina de vez e os dados parciais são apagados,
            mas o registo fica (estado «cancelado») e pode ser repetido;
- remover:  apaga só o registo (a transferência pára; ficheiros intactos);
- apagar ficheiro: remove o registo **e** os ficheiros do disco.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from nova_dm.core.engine import DownloadEngine
from nova_dm.core.models import AddRequest, DownloadRecord, DownloadStatus, EngineStatus, RequestContext
from nova_dm.database.repository import Repository
from nova_dm.errors import EngineError, NovaDMError
from nova_dm.utils.files import CONTROL_SUFFIX, category_for, delete_download_files
from nova_dm.utils.urls import redact_url

log = logging.getLogger(__name__)

PERSIST_INTERVAL = 2.0  # segundos entre gravações do progresso de transferências ativas

_STATE_MAP = {
    "active": DownloadStatus.ACTIVE,
    "waiting": DownloadStatus.QUEUED,
    "paused": DownloadStatus.PAUSED,
    "complete": DownloadStatus.COMPLETED,
    "error": DownloadStatus.FAILED,
    "removed": DownloadStatus.CANCELLED,
}


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class DownloadManager:
    def __init__(
        self,
        engine: DownloadEngine,
        repository: Repository,
        *,
        auto_resume: bool = True,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._engine = engine
        self._repo = repository
        self.auto_resume = auto_resume
        self._clock = clock
        self._records: dict[int, DownloadRecord] = {}
        self._contexts: dict[int, RequestContext] = {}  # cookies/referer do navegador: só em memória
        self._last_saved: dict[int, float] = {}

    # Consulta --------------------------------------------------------

    def records(self) -> list[DownloadRecord]:
        """Cópias dos registos (seguras para enviar para outra thread)."""
        return [replace(r) for r in sorted(self._records.values(), key=lambda r: (r.position, r.id or 0))]

    def get(self, download_id: int) -> DownloadRecord:
        try:
            return self._records[download_id]
        except KeyError as exc:
            raise NovaDMError(f"A transferência {download_id} já não existe.") from exc

    def reserved_names(self, directory: str) -> set[str]:
        """Nomes já usados por outras transferências na mesma pasta."""
        return {r.filename for r in self._records.values() if r.directory == directory}

    # Arranque --------------------------------------------------------

    def startup(self) -> None:
        """Carrega os registos e reconcilia-os com o estado real (motor + disco)."""
        self._records = {r.id: r for r in self._repo.list_downloads() if r.id is not None}
        self._reconcile()

    def _reconcile(self) -> None:
        for record in list(self._records.values()):
            if not record.status.is_pending:
                continue
            target = Path(record.directory) / record.filename
            control = target.with_name(target.name + CONTROL_SUFFIX)
            was_paused = record.status is DownloadStatus.PAUSED
            record.gid = None
            record.download_speed = 0
            if (
                target.is_file()
                and not control.exists()
                and record.total_bytes > 0
                and target.stat().st_size == record.total_bytes
            ):
                log.info("Transferência %s já estava concluída no disco", record.id)
                self._finish_completed(record)
                self._save(record)
                continue
            start = self.auto_resume and not was_paused
            try:
                self._submit(record, paused=not start)
            except EngineError as exc:
                log.error("Não foi possível retomar a transferência %s: %s", record.id, exc)
                record.status = DownloadStatus.FAILED
                record.error_message = str(exc)
            self._save(record)

    # Ações -----------------------------------------------------------

    def add(
        self,
        url: str,
        directory: Path,
        filename: str,
        *,
        connections: int,
        speed_limit: int = 0,
        start: bool = True,
        context: RequestContext | None = None,
    ) -> DownloadRecord:
        record = DownloadRecord(
            url=url,
            filename=filename,
            directory=str(directory),
            connections=connections,
            speed_limit=speed_limit,
            category=category_for(filename),
        )
        self._repo.add(record)
        assert record.id is not None
        if context is not None:
            self._contexts[record.id] = context
        try:
            self._submit(record, paused=not start)
        except EngineError:
            self._repo.delete(record.id)
            raise
        self._records[record.id] = record
        self._save(record)
        log.info("Transferência %s adicionada: %s", record.id, redact_url(url))
        return replace(record)

    def pause(self, download_id: int) -> None:
        record = self.get(download_id)
        if record.status not in (DownloadStatus.ACTIVE, DownloadStatus.QUEUED) or not record.gid:
            raise NovaDMError("Só é possível pausar transferências em curso ou em fila.")
        self._engine.pause(record.gid)
        record.status = DownloadStatus.PAUSED
        record.download_speed = 0
        self._save(record)

    def resume(self, download_id: int) -> None:
        record = self.get(download_id)
        if record.status in (DownloadStatus.FAILED, DownloadStatus.CANCELLED):
            self.retry(download_id)
            return
        if record.status is not DownloadStatus.PAUSED:
            raise NovaDMError("Só é possível retomar transferências pausadas.")
        if record.gid:
            self._engine.resume(record.gid)
        else:
            self._submit(record, paused=False)
        record.status = DownloadStatus.QUEUED
        self._save(record)

    def cancel(self, download_id: int) -> None:
        record = self.get(download_id)
        if not record.status.is_pending:
            raise NovaDMError("Só é possível cancelar transferências por concluir.")
        self._forget_in_engine(record)
        delete_download_files(record.directory, record.filename)
        record.status = DownloadStatus.CANCELLED
        record.completed_bytes = 0
        record.download_speed = 0
        record.error_message = ""
        self._save(record)

    def retry(self, download_id: int) -> None:
        record = self.get(download_id)
        if record.status not in (DownloadStatus.FAILED, DownloadStatus.CANCELLED):
            raise NovaDMError("Só é possível repetir transferências falhadas ou canceladas.")
        record.error_message = ""
        record.completed_at = None
        if record.status is DownloadStatus.CANCELLED:
            record.completed_bytes = 0
        self._submit(record, paused=False)
        record.status = DownloadStatus.QUEUED
        self._save(record)

    def remove(self, download_id: int, *, delete_files: bool = False) -> None:
        record = self.get(download_id)
        if record.status.is_pending:
            self._forget_in_engine(record)
        if delete_files:
            delete_download_files(record.directory, record.filename)
        self._repo.delete(download_id)
        self._records.pop(download_id, None)
        self._last_saved.pop(download_id, None)

    # Ordem -----------------------------------------------------------

    def _ordered_ids(self) -> list[int]:
        return [r.id for r in sorted(self._records.values(), key=lambda r: (r.position, r.id or 0)) if r.id is not None]

    def move(self, ids: list[int], where: str) -> None:
        """Move a seleção «up», «down», «top» ou «bottom» (mantém a ordem relativa entre os selecionados)."""
        order = self._ordered_ids()
        chosen = {i for i in ids if i in self._records}
        if where == "top":
            order = [i for i in order if i in chosen] + [i for i in order if i not in chosen]
        elif where == "bottom":
            order = [i for i in order if i not in chosen] + [i for i in order if i in chosen]
        elif where == "up":
            for k in range(1, len(order)):
                if order[k] in chosen and order[k - 1] not in chosen:
                    order[k - 1], order[k] = order[k], order[k - 1]
        elif where == "down":
            for k in range(len(order) - 2, -1, -1):
                if order[k] in chosen and order[k + 1] not in chosen:
                    order[k], order[k + 1] = order[k + 1], order[k]
        else:
            raise ValueError(f"Movimento desconhecido: {where}")
        self._apply_order(order)

    def move_to(self, ids: list[int], target_id: int | None, *, after: bool) -> None:
        """Coloca a seleção antes (ou depois) da transferência `target_id`; `None` = no fim."""
        chosen = [i for i in self._ordered_ids() if i in set(ids)]
        if not chosen or target_id in chosen:
            return
        rest = [i for i in self._ordered_ids() if i not in chosen]
        if target_id is None or target_id not in rest:
            index = len(rest)
        else:
            index = rest.index(target_id) + (1 if after else 0)
        self._apply_order(rest[:index] + chosen + rest[index:])

    def _apply_order(self, order: list[int]) -> None:
        for position, download_id in enumerate(order, start=1):
            record = self._records[download_id]
            if record.position != position:
                record.position = position
                self._save(record)
        gids = [self._records[i].gid for i in order if self._records[i].status.is_pending and self._records[i].gid]
        try:
            self._engine.reorder([g for g in gids if g])
        except EngineError as exc:
            log.warning("Não foi possível reordenar a fila no motor: %s", exc)

    # Sincronização ---------------------------------------------------

    def poll(self) -> list[DownloadRecord]:
        statuses = {s.gid: s for s in self._engine.snapshot()}
        now = self._clock()
        for record in self._records.values():
            if not record.status.is_pending or not record.gid:
                continue
            previous = record.status
            self._apply(record, statuses.get(record.gid))
            last = self._last_saved.get(record.id or 0, 0.0)
            if record.status is not previous or now - last >= PERSIST_INTERVAL:
                self._save(record)
        return self.records()

    def _apply(self, record: DownloadRecord, state: EngineStatus | None) -> None:
        if state is None:
            log.warning("A transferência %s desapareceu do motor", record.id)
            record.status = DownloadStatus.FAILED
            record.error_message = "A transferência desapareceu do motor de downloads."
            record.gid = None
            record.download_speed = 0
            return
        record.total_bytes = state.total_bytes or record.total_bytes
        record.completed_bytes = state.completed_bytes
        record.download_speed = state.download_speed
        record.connections = state.connections or record.connections
        new_status = _STATE_MAP.get(state.state, record.status)
        record.status = new_status
        if new_status.is_finished:
            record.download_speed = 0
            if new_status is DownloadStatus.COMPLETED:
                self._finish_completed(record)
            elif new_status is DownloadStatus.FAILED:
                detail = state.error_message or "Erro desconhecido"
                record.error_message = f"{detail} (código {state.error_code})" if state.error_code else detail
                log.warning("Transferência %s falhou: %s", record.id, record.error_message)
            self._forget_in_engine(record)

    def _finish_completed(self, record: DownloadRecord) -> None:
        record.status = DownloadStatus.COMPLETED
        record.completed_bytes = record.total_bytes or record.completed_bytes
        record.download_speed = 0
        record.error_message = ""
        record.completed_at = record.completed_at or _now_iso()
        record.gid = None

    def set_global_options(self, *, max_concurrent: int, download_limit: int) -> None:
        self._engine.set_global_options(max_concurrent=max_concurrent, download_limit=download_limit)

    # Encerramento ----------------------------------------------------

    def shutdown(self) -> None:
        """Grava o estado e pára o motor. As transferências por concluir ficam pendentes."""
        for record in self._records.values():
            record.download_speed = 0
            self._save(record)
        self._engine.stop()

    # Internos --------------------------------------------------------

    def _submit(self, record: DownloadRecord, *, paused: bool) -> None:
        record.gid = self._engine.add(
            AddRequest(
                url=record.url,
                directory=record.directory,
                filename=record.filename,
                connections=record.connections or 4,
                speed_limit=record.speed_limit,
                paused=paused,
                context=self._contexts.get(record.id) if record.id is not None else None,
            )
        )
        record.status = DownloadStatus.PAUSED if paused else DownloadStatus.QUEUED

    def _forget_in_engine(self, record: DownloadRecord) -> None:
        gid, record.gid = record.gid, None
        if gid:
            try:
                self._engine.forget(gid)
            except EngineError as exc:
                log.warning("Não foi possível limpar %s no motor: %s", gid, exc)

    def _save(self, record: DownloadRecord) -> None:
        self._repo.save(record)
        if record.id is not None:
            self._last_saved[record.id] = self._clock()
