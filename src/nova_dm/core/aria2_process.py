"""Arranque e paragem seguros do processo aria2c.

- O RPC escuta apenas em 127.0.0.1, numa porta livre escolhida no arranque.
- O segredo RPC é aleatório e vai num ficheiro de configuração com permissões 0600
  (nunca na linha de comandos, onde outros utilizadores o poderiam ler).
- `--stop-with-process` faz o aria2 terminar sozinho se a aplicação morrer.
"""

from __future__ import annotations

import logging
import os
import secrets
import shutil
import socket
import subprocess
import tempfile
import time
from pathlib import Path

from nova_dm.core.aria2_client import Aria2RpcClient
from nova_dm.errors import EngineError, EngineUnavailableError

log = logging.getLogger(__name__)

STARTUP_TIMEOUT = 15.0


def find_aria2(custom_path: str = "") -> str:
    candidate = custom_path.strip()
    if candidate:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
        raise EngineUnavailableError(f"O executável do aria2 indicado não existe: {candidate}")
    found = shutil.which("aria2c")
    if not found:
        raise EngineUnavailableError(
            "O aria2 (aria2c) não foi encontrado. Instale-o (por exemplo `sudo dnf install aria2`) "
            "ou indique o caminho nas definições."
        )
    return found


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class Aria2Process:
    def __init__(self, executable: str, log_file: Path | None = None, max_concurrent: int = 3) -> None:
        self._executable = executable
        self._log_file = log_file
        self._max_concurrent = max_concurrent
        self._proc: subprocess.Popen[bytes] | None = None
        self._runtime_dir: Path | None = None
        self.client: Aria2RpcClient | None = None

    @property
    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start(self) -> Aria2RpcClient:
        if self.is_running and self.client is not None:
            return self.client
        port = _free_port()
        secret = secrets.token_urlsafe(32)
        self._runtime_dir = Path(tempfile.mkdtemp(prefix="nova-dm-aria2-"))
        os.chmod(self._runtime_dir, 0o700)
        conf = self._runtime_dir / "aria2.conf"
        fd = os.open(conf, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(self._config_text(port, secret))

        log.info("A arrancar o aria2 em 127.0.0.1:%d", port)
        try:
            self._proc = subprocess.Popen(  # noqa: S603 - executável resolvido por find_aria2
                [self._executable, f"--conf-path={conf}", f"--stop-with-process={os.getpid()}"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                cwd=self._runtime_dir,
            )
        except OSError as exc:
            self._cleanup_runtime_dir()
            raise EngineUnavailableError(f"Não foi possível executar o aria2: {exc}") from exc

        client = Aria2RpcClient(port, secret)
        deadline = time.monotonic() + STARTUP_TIMEOUT
        while time.monotonic() < deadline:
            if self._proc.poll() is not None:
                detail = self._read_stderr()
                self._cleanup_runtime_dir()
                raise EngineUnavailableError(f"O aria2 terminou ao arrancar. {detail}".strip())
            try:
                version = client.get_version()
            except EngineError:
                time.sleep(0.1)
                continue
            log.info("aria2 %s pronto", version)
            self.client = client
            return client
        self.stop()
        raise EngineUnavailableError("O aria2 não respondeu a tempo.")

    def _config_text(self, port: int, secret: str) -> str:
        lines = [
            "enable-rpc=true",
            f"rpc-listen-port={port}",
            "rpc-listen-all=false",
            "rpc-allow-origin-all=false",
            f"rpc-secret={secret}",
            "rpc-max-request-size=4M",
            f"max-concurrent-downloads={self._max_concurrent}",
            "continue=true",
            "allow-overwrite=false",
            "auto-file-renaming=false",
            "file-allocation=none",
            "max-tries=5",
            "retry-wait=3",
            "split=4",
            "min-split-size=1M",
            "check-certificate=true",
            "summary-interval=0",
            "console-log-level=warn",
            "user-agent=NovaDM/0.1",
            "disable-ipv6=false",
        ]
        if self._log_file is not None:
            self._log_file.parent.mkdir(parents=True, exist_ok=True)
            lines += [f"log={self._log_file}", "log-level=warn"]
        return "\n".join(lines) + "\n"

    def _read_stderr(self) -> str:
        if self._proc is None or self._proc.stderr is None:
            return ""
        try:
            return self._proc.stderr.read(2000).decode("utf-8", "replace")
        except OSError:
            return ""

    def stop(self) -> None:
        proc, self._proc = self._proc, None
        client, self.client = self.client, None
        if proc is not None and proc.poll() is None:
            if client is not None:
                try:
                    client.shutdown()
                except EngineError as exc:
                    log.debug("Encerramento gracioso do aria2 falhou: %s", exc)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                log.warning("O aria2 não terminou a tempo; a enviar SIGTERM")
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    log.error("O aria2 não respondeu ao SIGTERM; a enviar SIGKILL")
                    proc.kill()
                    proc.wait()
        if proc is not None and proc.stderr is not None:
            proc.stderr.close()
        self._cleanup_runtime_dir()

    def _cleanup_runtime_dir(self) -> None:
        if self._runtime_dir is not None:
            shutil.rmtree(self._runtime_dir, ignore_errors=True)
            self._runtime_dir = None
