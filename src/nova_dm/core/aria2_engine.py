"""Implementação de DownloadEngine sobre o aria2 (JSON-RPC)."""

from __future__ import annotations

import logging
from typing import Any

from nova_dm.core.aria2_client import Aria2RpcClient
from nova_dm.core.aria2_process import Aria2Process, find_aria2
from nova_dm.core.engine import DownloadEngine
from nova_dm.core.models import AddRequest, EngineStatus
from nova_dm.errors import EngineError, EngineUnavailableError, RpcError

log = logging.getLogger(__name__)

MAX_CONNECTIONS_PER_SERVER = 16  # limite do próprio aria2


def _is_not_found(exc: RpcError) -> bool:
    return exc.code == 1 and "not found" in exc.rpc_message.lower()


def _to_status(item: dict[str, Any]) -> EngineStatus:
    files = item.get("files") or []
    path = str(files[0].get("path", "")) if files else ""
    return EngineStatus(
        gid=str(item["gid"]),
        state=str(item.get("status", "")),
        total_bytes=int(item.get("totalLength", 0) or 0),
        completed_bytes=int(item.get("completedLength", 0) or 0),
        download_speed=int(item.get("downloadSpeed", 0) or 0),
        connections=int(item.get("connections", 0) or 0),
        error_code=int(item.get("errorCode", 0) or 0),
        error_message=str(item.get("errorMessage", "") or ""),
        path=path,
    )


class Aria2Engine(DownloadEngine):
    def __init__(self, executable_path: str = "", log_file: Any = None, max_concurrent: int = 3) -> None:
        self._executable_path = executable_path
        self._log_file = log_file
        self._max_concurrent = max_concurrent
        self._process: Aria2Process | None = None

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.is_running

    def _client(self) -> Aria2RpcClient:
        if self._process is None or self._process.client is None or not self._process.is_running:
            raise EngineUnavailableError("O motor de downloads não está em execução.")
        return self._process.client

    def start(self) -> None:
        if self.is_running:
            return
        executable = find_aria2(self._executable_path)
        self._process = Aria2Process(executable, self._log_file, self._max_concurrent)
        self._process.start()

    def stop(self) -> None:
        if self._process is not None:
            self._process.stop()
            self._process = None

    def add(self, request: AddRequest) -> str:
        options: dict[str, Any] = {
            "dir": request.directory,
            "out": request.filename,
            "split": str(max(1, min(request.connections, MAX_CONNECTIONS_PER_SERVER))),
            "max-connection-per-server": str(max(1, min(request.connections, MAX_CONNECTIONS_PER_SERVER))),
            "continue": "true",
            "pause": "true" if request.paused else "false",
        }
        if request.speed_limit > 0:
            options["max-download-limit"] = str(request.speed_limit)
        ctx = request.context
        if ctx is not None:
            if ctx.referer:
                options["referer"] = ctx.referer
            if ctx.user_agent:
                options["user-agent"] = ctx.user_agent
            if ctx.cookies:
                options["header"] = [f"Cookie: {ctx.cookies}"]
        return self._client().add_uri(request.url, options)

    def pause(self, gid: str) -> None:
        self._client().pause(gid)

    def resume(self, gid: str) -> None:
        self._client().unpause(gid)

    def forget(self, gid: str) -> None:
        client = self._client()
        try:
            client.force_remove(gid)
        except RpcError as exc:
            if not _is_not_found(exc):
                raise
            log.debug("forceRemove: %s não está ativa (já terminada?)", gid)
        try:
            client.remove_download_result(gid)
        except RpcError as exc:
            if not _is_not_found(exc):
                raise
            log.debug("removeDownloadResult: %s já não existe", gid)

    def reorder(self, gids: list[str]) -> None:
        client = self._client()
        waiting = {s.gid for s in self.snapshot() if s.state in ("waiting", "paused")}
        for index, gid in enumerate(g for g in gids if g in waiting):
            try:
                client.change_position(gid, index)
            except RpcError as exc:
                if not _is_not_found(exc):
                    raise

    def snapshot(self) -> list[EngineStatus]:
        try:
            return [_to_status(item) for item in self._client().snapshot()]
        except KeyError as exc:
            raise EngineError(f"Resposta inesperada do aria2 (falta o campo {exc})") from exc

    def set_global_options(self, *, max_concurrent: int | None = None, download_limit: int | None = None) -> None:
        options: dict[str, str] = {}
        if max_concurrent is not None:
            options["max-concurrent-downloads"] = str(max(1, max_concurrent))
        if download_limit is not None:
            options["max-overall-download-limit"] = str(max(0, download_limit))
        if options:
            self._client().change_global_option(options)
