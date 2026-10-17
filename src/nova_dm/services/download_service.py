"""Serviço de aplicação: valida pedidos do utilizador e orquestra o gestor de downloads.

Sem Qt; usado a partir da thread do motor (ver `download_controller`).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from nova_dm.config import Settings
from nova_dm.core.download_manager import DownloadManager
from nova_dm.core.models import DownloadRecord, RequestContext
from nova_dm.errors import NovaDMError
from nova_dm.utils.files import (
    check_free_space,
    sanitize_filename,
    unique_filename,
    validate_directory,
)
from nova_dm.utils.urls import filename_from_url, validate_url

log = logging.getLogger(__name__)


@dataclass(slots=True)
class AddResult:
    added: list[DownloadRecord] = field(default_factory=list)
    errors: list[tuple[str, str]] = field(default_factory=list)  # (url, mensagem)


class DownloadService:
    def __init__(self, manager: DownloadManager, settings: Settings) -> None:
        self._manager = manager
        self.settings = settings

    def add_many(
        self,
        urls: list[str],
        directory: str,
        *,
        filename: str = "",
        connections: int | None = None,
        size_hint: int = 0,
        start: bool = True,
        context: RequestContext | None = None,
    ) -> AddResult:
        """Adiciona vários URLs. O nome só é respeitado quando há exatamente um URL."""
        result = AddResult()
        try:
            target_dir = validate_directory(directory)
        except NovaDMError as exc:
            result.errors = [(url, str(exc)) for url in urls] or [("", str(exc))]
            return result

        chosen_connections = connections or self.settings.connections_per_download
        reserved = self._manager.reserved_names(str(target_dir))
        for raw in urls:
            try:
                url = validate_url(raw)
                wanted = filename if (filename and len(urls) == 1) else filename_from_url(url)
                name = unique_filename(target_dir, sanitize_filename(wanted), reserved)
                if len(urls) == 1:
                    check_free_space(target_dir, size_hint)
                record = self._manager.add(
                    url, target_dir, name, connections=chosen_connections, start=start,
                    context=context,
                )
            except NovaDMError as exc:
                log.warning("Não foi possível adicionar o URL: %s", exc)
                result.errors.append((raw, str(exc)))
                continue
            reserved.add(name)
            result.added.append(record)
        return result

    def apply_settings(self, settings: Settings) -> None:
        """Aplica as definições ao motor em funcionamento."""
        self.settings = settings
        self._manager.auto_resume = settings.auto_resume
        self._manager.set_global_options(
            max_concurrent=settings.max_concurrent,
            download_limit=settings.global_speed_limit_bytes,
        )

    def pause(self, download_id: int) -> None:
        self._manager.pause(download_id)

    def resume(self, download_id: int) -> None:
        self._manager.resume(download_id)

    def cancel(self, download_id: int) -> None:
        self._manager.cancel(download_id)

    def retry(self, download_id: int) -> None:
        self._manager.retry(download_id)

    def remove(self, download_id: int, *, delete_files: bool = False) -> None:
        self._manager.remove(download_id, delete_files=delete_files)

    def move(self, ids: list[int], where: str) -> None:
        self._manager.move(ids, where)

    def move_to(self, ids: list[int], target_id: int | None, after: bool) -> None:
        self._manager.move_to(ids, target_id, after=after)

    def poll(self) -> list[DownloadRecord]:
        return self._manager.poll()

    def records(self) -> list[DownloadRecord]:
        return self._manager.records()

    def shutdown(self) -> None:
        self._manager.shutdown()
