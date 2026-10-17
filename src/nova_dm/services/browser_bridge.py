"""Recetor local para a integração com o navegador.

O Nova DM escuta num servidor HTTP **apenas em 127.0.0.1** e recebe links enviados por uma extensão
do navegador (ver ``browser-extension/firefox``). A extensão pode enviar também o referer, o user-agent
e os cookies do pedido original, para que downloads com sessão iniciada funcionem; esses dados só
vivem em memória e nunca são registados.

Segurança (um servidor local é um alvo para páginas web maliciosas):
- só aceita ligações a 127.0.0.1 e verifica o cabeçalho Host (contra DNS rebinding);
- exige o token secreto (`Authorization: Bearer <token>`), comparado em tempo constante;
- rejeita pedidos com `Origin` que não seja de uma extensão (páginas web enviam sempre `Origin`);
- não envia cabeçalhos CORS, por isso nenhuma página consegue ler respostas;
- limita o tamanho do pedido e só aceita URLs http(s) válidos;
- por omissão os links **não** são descarregados diretamente: abrem o diálogo «Adicionar download»
  para confirmação (a opção «perguntar antes de adicionar» pode ser desligada pelo utilizador).
"""

from __future__ import annotations

import hmac
import json
import logging
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from PySide6.QtCore import QObject, Signal

from nova_dm.errors import InvalidUrlError
from nova_dm.utils.urls import validate_url

log = logging.getLogger(__name__)

MAX_BODY_BYTES = 64 * 1024
MAX_LINKS = 200
PAIR_TIMEOUT_SECONDS = 60
PAIR_COOLDOWN_SECONDS = 3.0
MAX_COOKIE_CHARS = 8192
MAX_UA_CHARS = 512
MAX_NAME_CHARS = 255
_EXTENSION_ORIGINS = ("chrome-extension://", "moz-extension://", "safari-web-extension://")


def _clean_header(value: object, limit: int) -> str:
    """Texto seguro para um cabeçalho HTTP: sem controlo/quebras de linha e com tamanho limitado."""
    if not isinstance(value, str) or len(value) > limit:
        return ""
    return value if value.isprintable() else ""


def parse_context(data: dict[str, object]) -> dict[str, str]:
    """Extrai o contexto opcional do pedido (referer, user_agent, cookies, filename)."""
    referer = ""
    raw_referer = data.get("referer")
    if isinstance(raw_referer, str) and raw_referer:
        try:
            referer = validate_url(raw_referer)
        except InvalidUrlError:
            referer = ""
    return {
        "referer": referer,
        "user_agent": _clean_header(data.get("user_agent"), MAX_UA_CHARS),
        "cookies": _clean_header(data.get("cookies"), MAX_COOKIE_CHARS),
        "filename": _clean_header(data.get("filename"), MAX_NAME_CHARS),
    }


class _PairRequest:
    def __init__(self) -> None:
        self.event = threading.Event()
        self.allowed = False


def generate_token() -> str:
    return secrets.token_urlsafe(24)


class BrowserBridge(QObject):
    links_received = Signal(list, dict)  # URLs válidos + contexto (emitido na thread principal, via fila Qt)
    failed = Signal(str)
    pair_requested = Signal(str)  # origem da extensão; a janela pergunta ao utilizador e chama answer_pair

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._config: tuple[int, str] | None = None
        self._pair_lock = threading.Lock()
        self._pair: _PairRequest | None = None
        self._last_pair_end = 0.0

    @property
    def is_running(self) -> bool:
        return self._server is not None

    def apply(self, enabled: bool, port: int, token: str) -> None:
        """Liga, desliga ou reinicia o recetor conforme as definições."""
        wanted = (port, token) if enabled and token else None
        if wanted == self._config and (wanted is None) == (self._server is None):
            return
        self.stop()
        if wanted is None:
            return
        try:
            self._server = ThreadingHTTPServer(("127.0.0.1", port), self._make_handler(token))
        except OSError as exc:
            log.warning("Integração com o navegador: não foi possível usar a porta %d: %s", port, exc)
            self.failed.emit(str(exc))
            return
        self._server.daemon_threads = True
        self._config = wanted
        self._thread = threading.Thread(target=self._server.serve_forever, name="nova-dm-browser", daemon=True)
        self._thread.start()
        log.info("Integração com o navegador ativa em 127.0.0.1:%d", port)

    def answer_pair(self, allowed: bool) -> None:
        """Resposta do utilizador ao pedido de emparelhamento (chamar na thread principal)."""
        pending = self._pair
        if pending is not None:
            pending.allowed = allowed
            pending.event.set()

    def stop(self) -> None:
        self.answer_pair(False)
        server, thread = self._server, self._thread
        self._server = self._thread = self._config = None
        if server is not None:
            server.shutdown()
            server.server_close()
        if thread is not None:
            thread.join(timeout=2)

    def _make_handler(self, token: str) -> type[BaseHTTPRequestHandler]:
        bridge = self
        expected = f"Bearer {token}".encode()

        class Handler(BaseHTTPRequestHandler):
            server_version = "NovaDM"
            sys_version = ""

            def log_message(self, format: str, *args: object) -> None:  # noqa: A002 - sem registar cabeçalhos
                return

            def _reply(self, status: int, payload: dict[str, object]) -> None:
                body = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def _authorized(self) -> bool:
                host = (self.headers.get("Host") or "").lower()
                if host not in (f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"):
                    return False
                origin = self.headers.get("Origin")
                if origin is not None and not origin.startswith(_EXTENSION_ORIGINS):
                    return False
                supplied = (self.headers.get("Authorization") or "").encode()
                return hmac.compare_digest(supplied, expected)

            def do_GET(self) -> None:  # noqa: N802
                if not self._authorized():
                    self._reply(403, {"error": "forbidden"})
                elif self.path == "/v1/ping":
                    self._reply(200, {"app": "Nova DM", "api": 1})
                else:
                    self._reply(404, {"error": "not found"})

            def _pair_flow(self) -> None:
                """Emparelhamento: entrega o token à extensão só se o utilizador confirmar na aplicação."""
                host = (self.headers.get("Host") or "").lower()
                origin = self.headers.get("Origin") or ""
                if host not in (f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}") \
                        or not origin.startswith(_EXTENSION_ORIGINS):
                    self._reply(403, {"error": "forbidden"})
                    return
                with bridge._pair_lock:
                    if bridge._pair is not None or time.monotonic() - bridge._last_pair_end < PAIR_COOLDOWN_SECONDS:
                        self._reply(429, {"error": "busy"})
                        return
                    pending = bridge._pair = _PairRequest()
                try:
                    bridge.pair_requested.emit(origin)
                    answered = pending.event.wait(PAIR_TIMEOUT_SECONDS)
                finally:
                    with bridge._pair_lock:
                        bridge._pair = None
                        bridge._last_pair_end = time.monotonic()
                if answered and pending.allowed:
                    self._reply(200, {"token": token})
                else:
                    self._reply(403, {"error": "denied"})

            def do_POST(self) -> None:  # noqa: N802
                if self.path == "/v1/pair":
                    self._pair_flow()
                    return
                if not self._authorized():
                    self._reply(403, {"error": "forbidden"})
                    return
                if self.path != "/v1/links":
                    self._reply(404, {"error": "not found"})
                    return
                try:
                    length = int(self.headers.get("Content-Length") or "0")
                except ValueError:
                    length = -1
                if not 0 < length <= MAX_BODY_BYTES:
                    self._reply(413 if length > MAX_BODY_BYTES else 400, {"error": "invalid body size"})
                    return
                try:
                    data = json.loads(self.rfile.read(length))
                    raw = data["urls"]
                    if not isinstance(raw, list):
                        raise TypeError
                except (ValueError, KeyError, TypeError):
                    self._reply(400, {"error": "expected JSON {\"urls\": [...]}"})
                    return
                urls: dict[str, None] = {}
                for item in raw[:MAX_LINKS]:
                    if isinstance(item, str):
                        try:
                            urls.setdefault(validate_url(item), None)
                        except InvalidUrlError:
                            continue
                if not urls:
                    self._reply(400, {"error": "no valid http(s) links"})
                    return
                bridge.links_received.emit(list(urls), parse_context(data))
                self._reply(200, {"accepted": len(urls)})

        return Handler
