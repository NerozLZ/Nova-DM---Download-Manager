"""Ponte entre a interface (thread principal) e o motor (thread própria).

Todas as operações de rede/disco/RPC correm numa QThread; a interface só envia
pedidos por sinais (filas Qt) e recebe cópias dos registos. Assim a UI nunca bloqueia.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QMetaObject, QObject, Qt, QThread, QTimer, Signal, Slot

from nova_dm.config import AppPaths, Settings
from nova_dm.core.aria2_engine import Aria2Engine
from nova_dm.core.download_manager import DownloadManager
from nova_dm.core.engine import DownloadEngine
from nova_dm.core.models import RequestContext
from nova_dm.database.repository import Repository
from nova_dm.errors import EngineError, NovaDMError
from nova_dm.i18n import tr
from nova_dm.services.download_service import DownloadService

log = logging.getLogger(__name__)

POLL_INTERVAL_MS = 500
_ACTIONS = {"pause", "resume", "cancel", "retry", "remove", "delete_files"}

EngineFactory = Callable[[Settings, AppPaths], DownloadEngine]


def default_engine_factory(settings: Settings, paths: AppPaths) -> DownloadEngine:
    return Aria2Engine(settings.aria2_path, paths.aria2_log_file, settings.max_concurrent)


class _Worker(QObject):
    records = Signal(list)
    error = Signal(str)
    ready = Signal()
    failed = Signal(str)
    added = Signal(object)

    def __init__(self, repo: Repository, paths: AppPaths, settings: Settings, factory: EngineFactory) -> None:
        super().__init__()
        self._repo = repo
        self._paths = paths
        self._settings = settings
        self._factory = factory
        self._engine: DownloadEngine | None = None
        self._service: DownloadService | None = None
        self._timer: QTimer | None = None

    @Slot()
    def start(self) -> None:
        try:
            self._engine = self._factory(self._settings, self._paths)
            self._engine.start()
            manager = DownloadManager(self._engine, self._repo, auto_resume=self._settings.auto_resume)
            manager.startup()
            self._service = DownloadService(manager, self._settings)
            self._service.apply_settings(self._settings)
        except NovaDMError as exc:
            log.error("O motor de downloads não arrancou: %s", exc)
            self.failed.emit(str(exc))
            return
        except Exception:  # noqa: BLE001 - fronteira da thread: regista com traceback e informa a UI
            log.exception("Falha inesperada ao arrancar o motor")
            self.failed.emit(tr("Unexpected error while starting the download engine. See the log for details."))
            return
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._timer.start(POLL_INTERVAL_MS)
        self.ready.emit()
        self._poll()

    @Slot()
    def _poll(self) -> None:
        if self._service is None:
            return
        try:
            self.records.emit(self._service.poll())
        except EngineError as exc:
            log.error("Perda de ligação ao motor: %s", exc)
            if self._timer is not None:
                self._timer.stop()
            self.failed.emit(tr("The download engine stopped responding: {error}").format(error=exc))

    @Slot(str, object)
    def run(self, action: str, ids: object) -> None:
        if action not in _ACTIONS:
            raise ValueError(f"Ação desconhecida: {action}")
        if self._service is None:
            self.error.emit(tr("The download engine is not running."))
            return
        messages: list[str] = []
        for download_id in ids:  # type: ignore[attr-defined]
            try:
                if action == "delete_files":
                    self._service.remove(download_id, delete_files=True)
                else:
                    getattr(self._service, action)(download_id)
            except NovaDMError as exc:
                messages.append(str(exc))
            except Exception:  # noqa: BLE001
                log.exception("Falha inesperada na ação %s", action)
                messages.append(tr("Unexpected error. See the log for details."))
        if messages:
            self.error.emit("\n".join(dict.fromkeys(messages)))
        self._poll()

    @Slot(str, object, object, bool)
    def reorder(self, how: str, ids: object, target: object, after: bool) -> None:
        if self._service is None:
            return
        try:
            if how == "move_to":
                self._service.move_to(list(ids), target, after)  # type: ignore[call-overload]
            else:
                self._service.move(list(ids), how)  # type: ignore[call-overload]
        except Exception:  # noqa: BLE001
            log.exception("Falha ao reordenar")
            self.error.emit(tr("Unexpected error. See the log for details."))
        self._poll()

    @Slot(object)
    def add(self, params: dict[str, Any]) -> None:
        if self._service is None:
            self.error.emit(tr("The download engine is not running."))
            return
        try:
            result = self._service.add_many(**params)
        except Exception:  # noqa: BLE001
            log.exception("Falha inesperada ao adicionar transferências")
            self.error.emit(tr("Unexpected error. See the log for details."))
            return
        self.added.emit(result)
        self._poll()

    @Slot(object)
    def apply_settings(self, settings: Settings) -> None:
        self._settings = settings
        if self._service is None:
            return
        try:
            self._service.apply_settings(settings)
        except EngineError as exc:
            self.error.emit(str(exc))

    @Slot()
    def shutdown(self) -> None:
        if self._timer is not None:
            self._timer.stop()
        try:
            if self._service is not None:
                self._service.shutdown()
            elif self._engine is not None:
                self._engine.stop()
        except Exception:  # noqa: BLE001
            log.exception("Falha ao encerrar o motor")
        finally:
            self._service = None


class DownloadController(QObject):
    records_changed = Signal(list)
    error = Signal(str)
    engine_ready = Signal()
    engine_failed = Signal(str)
    add_finished = Signal(object)

    _start = Signal()
    _run = Signal(str, object)
    _add = Signal(object)
    _reorder = Signal(str, object, object, bool)
    _apply = Signal(object)

    def __init__(
        self,
        repo: Repository,
        paths: AppPaths,
        settings: Settings,
        engine_factory: EngineFactory = default_engine_factory,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._thread = QThread(self)
        self._thread.setObjectName("nova-dm-engine")
        self._worker = _Worker(repo, paths, settings, engine_factory)
        self._worker.moveToThread(self._thread)
        self._start.connect(self._worker.start)
        self._run.connect(self._worker.run)
        self._add.connect(self._worker.add)
        self._reorder.connect(self._worker.reorder)
        self._apply.connect(self._worker.apply_settings)
        self._worker.records.connect(self.records_changed)
        self._worker.error.connect(self.error)
        self._worker.ready.connect(self.engine_ready)
        self._worker.failed.connect(self.engine_failed)
        self._worker.added.connect(self.add_finished)
        self._stopped = False

    def start(self) -> None:
        self._thread.start()
        self._start.emit()

    def add(self, urls: list[str], directory: str, *, filename: str = "", connections: int | None = None,
            size_hint: int = 0, start: bool = True, context: RequestContext | None = None) -> None:
        self._add.emit(
            {"urls": urls, "directory": directory, "filename": filename, "connections": connections,
             "size_hint": size_hint, "start": start, "context": context}
        )

    def pause(self, ids: list[int]) -> None:
        self._run.emit("pause", list(ids))

    def resume(self, ids: list[int]) -> None:
        self._run.emit("resume", list(ids))

    def cancel(self, ids: list[int]) -> None:
        self._run.emit("cancel", list(ids))

    def retry(self, ids: list[int]) -> None:
        self._run.emit("retry", list(ids))

    def remove(self, ids: list[int]) -> None:
        self._run.emit("remove", list(ids))

    def delete_files(self, ids: list[int]) -> None:
        self._run.emit("delete_files", list(ids))

    def move(self, ids: list[int], where: str) -> None:
        """where: up, down, top, bottom."""
        self._reorder.emit(where, list(ids), None, False)

    def move_to(self, ids: list[int], target_id: int | None, after: bool) -> None:
        self._reorder.emit("move_to", list(ids), target_id, after)

    def apply_settings(self, settings: Settings) -> None:
        self._apply.emit(settings)

    def shutdown(self) -> None:
        """Pára o motor (bloqueia até terminar) e a thread. Seguro chamar mais de uma vez."""
        if self._stopped:
            return
        self._stopped = True
        if self._thread.isRunning():
            QMetaObject.invokeMethod(self._worker, "shutdown", Qt.ConnectionType.BlockingQueuedConnection)
            self._thread.quit()
            self._thread.wait(10_000)
