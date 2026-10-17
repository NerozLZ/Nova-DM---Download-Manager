"""Servidor HTTP local para testes, com suporte a Range, redirecionamentos e limitação de ritmo."""

from __future__ import annotations

import hashlib
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def make_payload(size: int, seed: int = 7) -> bytes:
    """Conteúdo determinístico (não repetitivo) de `size` bytes."""
    block = hashlib.sha256(str(seed).encode()).digest()
    out = bytearray()
    while len(out) < size:
        block = hashlib.sha256(block).digest()
        out += block
    return bytes(out[:size])


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args: object) -> None:  # silencioso
        pass

    @property
    def cfg(self) -> TestServer:
        return self.server.cfg  # type: ignore[attr-defined]

    def _send_file(self, body: bytes, head_only: bool) -> None:
        total = len(body)
        start, end, status = 0, total - 1, 200
        header = self.headers.get("Range")
        if header and self.cfg.ranges:
            match = re.match(r"bytes=(\d+)-(\d*)", header)
            if match:
                start = int(match.group(1))
                end = int(match.group(2)) if match.group(2) else total - 1
                end = min(end, total - 1)
                if start >= total:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{total}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                status = 206
        length = end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(length))
        if self.cfg.ranges:
            self.send_header("Accept-Ranges", "bytes")
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{total}")
        if self.cfg.disposition:
            self.send_header("Content-Disposition", f'attachment; filename="{self.cfg.disposition}"')
        self.end_headers()
        if head_only:
            return
        sent = 0
        chunk = self.cfg.chunk_size
        try:
            while sent < length:
                piece = body[start + sent : start + sent + min(chunk, length - sent)]
                self.wfile.write(piece)
                sent += len(piece)
                if self.cfg.delay:
                    time.sleep(self.cfg.delay)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _route(self, head_only: bool) -> None:
        path = self.path.split("?", 1)[0]
        with self.cfg.lock:
            self.cfg.requests.append((self.command, path, self.headers.get("Range")))
        if path.startswith("/file/"):
            name = path[len("/file/") :]
            body = self.cfg.files.get(name)
            if body is None:
                self.send_error(404)
                return
            self._send_file(body, head_only)
        elif path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/file/data.bin")
            self.send_header("Content-Length", "0")
            self.end_headers()
        elif path == "/error500":
            self.send_error(500)
        else:
            self.send_error(404)

    def do_GET(self) -> None:  # noqa: N802
        self._route(head_only=False)

    def do_HEAD(self) -> None:  # noqa: N802
        self._route(head_only=True)


class TestServer:
    __test__ = False  # evita que o pytest tente recolher a classe

    def __init__(self, *, ranges: bool = True, delay: float = 0.0, chunk_size: int = 65536, disposition: str = "") -> None:
        self.files: dict[str, bytes] = {}
        self.ranges = ranges
        self.delay = delay
        self.chunk_size = chunk_size
        self.disposition = disposition
        self.requests: list[tuple[str, str, str | None]] = []
        self.lock = threading.Lock()
        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._httpd.daemon_threads = True
        self._httpd.cfg = self  # type: ignore[attr-defined]
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._httpd.server_address[1]}"

    def url(self, name: str) -> str:
        return f"{self.base_url}/file/{name}"

    def __enter__(self) -> TestServer:
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
