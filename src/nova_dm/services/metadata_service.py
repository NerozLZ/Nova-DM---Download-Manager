"""Obtenção de metadados de um URL (nome, tamanho, suporte de retoma) antes de descarregar.

Usa apenas a biblioteca padrão. As funções bloqueiam: devem correr fora da thread da interface.
"""

from __future__ import annotations

import base64
import http.client
import logging
import re
from dataclasses import dataclass
from urllib.parse import unquote, urljoin, urlsplit

from nova_dm.errors import InvalidUrlError, ProbeError
from nova_dm.utils.files import sanitize_filename
from nova_dm.utils.urls import filename_from_url, redact_url, validate_url

log = logging.getLogger(__name__)

MAX_REDIRECTS = 10
_REDIRECT_CODES = (301, 302, 303, 307, 308)
_USER_AGENT = "NovaDM/0.1"


@dataclass(frozen=True, slots=True)
class UrlMetadata:
    url: str
    final_url: str
    filename: str
    size: int | None
    accepts_ranges: bool
    content_type: str


def _filename_from_disposition(value: str) -> str | None:
    match = re.search(r"filename\*\s*=\s*([^']*)'[^']*'([^;]+)", value, re.IGNORECASE)
    if match:
        try:
            return unquote(match.group(2).strip(), encoding=match.group(1).strip() or "utf-8")
        except LookupError:
            return unquote(match.group(2).strip())
    match = re.search(r'filename\s*=\s*"([^"]+)"', value, re.IGNORECASE) or re.search(
        r"filename\s*=\s*([^;]+)", value, re.IGNORECASE
    )
    return match.group(1).strip() if match else None


def _request(method: str, url: str, extra: dict[str, str], timeout: float) -> tuple[int, http.client.HTTPMessage]:
    parts = urlsplit(url)
    headers = {"User-Agent": _USER_AGENT, "Accept": "*/*", "Accept-Encoding": "identity", **extra}
    if parts.username:
        raw = f"{unquote(parts.username)}:{unquote(parts.password or '')}".encode()
        headers["Authorization"] = "Basic " + base64.b64encode(raw).decode("ascii")
    connection_class = http.client.HTTPSConnection if parts.scheme.lower() == "https" else http.client.HTTPConnection
    conn = connection_class(parts.hostname, parts.port, timeout=timeout)
    path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
    try:
        conn.request(method, path, headers=headers)
        response = conn.getresponse()
        return response.status, response.headers
    except (OSError, http.client.HTTPException) as exc:
        raise ProbeError(f"Não foi possível contactar o servidor: {exc}") from exc
    finally:
        conn.close()  # não lê o corpo: só interessam os cabeçalhos


def probe_url(url: str, timeout: float = 15.0) -> UrlMetadata:
    try:
        current = validate_url(url)
    except InvalidUrlError as exc:
        raise ProbeError(str(exc)) from exc

    for _ in range(MAX_REDIRECTS + 1):
        status, headers = _request("HEAD", current, {}, timeout)
        if status in (405, 501) or (status == 200 and headers.get("Content-Length") is None):
            status, headers = _request("GET", current, {"Range": "bytes=0-0"}, timeout)
        if status in _REDIRECT_CODES:
            location = headers.get("Location")
            if not location:
                raise ProbeError(f"Redirecionamento (HTTP {status}) sem destino.")
            try:
                current = validate_url(urljoin(current, location))
            except InvalidUrlError as exc:
                raise ProbeError(f"Redirecionamento inválido: {exc}") from exc
            continue
        if status >= 400:
            raise ProbeError(f"O servidor respondeu com o erro HTTP {status}.")
        return _build_metadata(url, current, status, headers)
    raise ProbeError("Demasiados redirecionamentos.")


def _build_metadata(original: str, final_url: str, status: int, headers: http.client.HTTPMessage) -> UrlMetadata:
    size: int | None = None
    content_range = headers.get("Content-Range", "")
    range_match = re.search(r"/(\d+)\s*$", content_range)
    if range_match:
        size = int(range_match.group(1))
    elif headers.get("Content-Length", "").isdigit() and status != 206:
        size = int(headers["Content-Length"])
    accepts = status == 206 or "bytes" in headers.get("Accept-Ranges", "").lower()
    disposition = headers.get("Content-Disposition", "")
    name = (_filename_from_disposition(disposition) if disposition else None) or filename_from_url(final_url)
    log.debug("Metadados de %s: tamanho=%s retoma=%s", redact_url(final_url), size, accepts)
    return UrlMetadata(
        url=original,
        final_url=final_url,
        filename=sanitize_filename(name),
        size=size,
        accepts_ranges=accepts,
        content_type=headers.get("Content-Type", "").split(";")[0].strip(),
    )
