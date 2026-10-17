"""Cliente JSON-RPC (sobre HTTP, apenas em localhost) para o aria2.

Cada chamada usa uma ligação nova, por isso o cliente é seguro entre threads.
O segredo RPC nunca é registado nos logs.
"""

from __future__ import annotations

import http.client
import itertools
import json
import logging
from typing import Any

from nova_dm.errors import EngineError, RpcError

log = logging.getLogger(__name__)

STATUS_KEYS = [
    "gid",
    "status",
    "totalLength",
    "completedLength",
    "downloadSpeed",
    "connections",
    "errorCode",
    "errorMessage",
    "files",
]


class Aria2RpcClient:
    def __init__(self, port: int, secret: str, host: str = "127.0.0.1", timeout: float = 10.0) -> None:
        if host not in ("127.0.0.1", "localhost", "::1"):
            raise ValueError("O cliente RPC só aceita ligações locais (loopback).")
        self._host = host
        self._port = port
        self._secret = secret
        self._timeout = timeout
        self._ids = itertools.count(1)

    def _token(self) -> str:
        return f"token:{self._secret}"

    def _post(self, payload: dict[str, Any]) -> Any:
        body = json.dumps(payload).encode("utf-8")
        conn = http.client.HTTPConnection(self._host, self._port, timeout=self._timeout)
        try:
            conn.request("POST", "/jsonrpc", body=body, headers={"Content-Type": "application/json"})
            response = conn.getresponse()
            raw = response.read()
        except (OSError, http.client.HTTPException) as exc:
            raise EngineError(f"Sem ligação ao aria2: {exc}") from exc
        finally:
            conn.close()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise EngineError(f"Resposta inválida do aria2 (HTTP {response.status})") from exc
        return data

    def call(self, method: str, *params: Any) -> Any:
        payload = {
            "jsonrpc": "2.0",
            "id": str(next(self._ids)),
            "method": f"aria2.{method}",
            "params": [self._token(), *params],
        }
        log.debug("RPC %s", method)
        data = self._post(payload)
        if "error" in data:
            err = data["error"]
            raise RpcError(int(err.get("code", -1)), str(err.get("message", "")))
        return data.get("result")

    def multicall(self, calls: list[tuple[str, list[Any]]]) -> list[Any]:
        """Executa várias chamadas num só pedido. Devolve os resultados na mesma ordem."""
        inner = [{"methodName": f"aria2.{name}", "params": [self._token(), *params]} for name, params in calls]
        payload = {"jsonrpc": "2.0", "id": str(next(self._ids)), "method": "system.multicall", "params": [inner]}
        data = self._post(payload)
        if "error" in data:
            err = data["error"]
            raise RpcError(int(err.get("code", -1)), str(err.get("message", "")))
        results: list[Any] = []
        for item in data.get("result", []):
            if isinstance(item, dict) and "faultCode" in item:
                raise RpcError(int(item["faultCode"]), str(item.get("faultString", "")))
            results.append(item[0] if isinstance(item, list) and item else item)
        return results

    # Atalhos tipados -------------------------------------------------

    def get_version(self) -> str:
        return str(self.call("getVersion")["version"])

    def add_uri(self, url: str, options: dict[str, Any]) -> str:
        return str(self.call("addUri", [url], options))

    def pause(self, gid: str) -> None:
        self.call("forcePause", gid)

    def unpause(self, gid: str) -> None:
        self.call("unpause", gid)

    def change_position(self, gid: str, position: int) -> None:
        self.call("changePosition", gid, position, "POS_SET")

    def force_remove(self, gid: str) -> None:
        self.call("forceRemove", gid)

    def remove_download_result(self, gid: str) -> None:
        self.call("removeDownloadResult", gid)

    def change_global_option(self, options: dict[str, str]) -> None:
        self.call("changeGlobalOption", options)

    def shutdown(self) -> None:
        self.call("shutdown")

    def snapshot(self, max_stopped: int = 1000) -> list[dict[str, Any]]:
        active, waiting, stopped = self.multicall(
            [
                ("tellActive", [STATUS_KEYS]),
                ("tellWaiting", [0, 1000, STATUS_KEYS]),
                ("tellStopped", [0, max_stopped, STATUS_KEYS]),
            ]
        )
        return [*active, *waiting, *stopped]
