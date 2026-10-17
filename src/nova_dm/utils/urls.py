"""Validação e tratamento de URLs."""

from __future__ import annotations

import re
from urllib.parse import unquote, urlsplit, urlunsplit

from nova_dm.errors import InvalidUrlError

_ALLOWED_SCHEMES = ("http", "https")
_WHITESPACE = re.compile(r"\s+")
_URL_IN_TEXT = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)


def validate_url(text: str) -> str:
    """Devolve o URL limpo ou levanta InvalidUrlError."""
    url = text.strip()
    if not url:
        raise InvalidUrlError("O URL está vazio.")
    if _WHITESPACE.search(url):
        raise InvalidUrlError("O URL não pode conter espaços.")
    try:
        parts = urlsplit(url)
        host = parts.hostname
        _ = parts.port  # valida a porta
    except ValueError as exc:
        raise InvalidUrlError(f"URL inválido: {exc}") from exc
    if parts.scheme.lower() not in _ALLOWED_SCHEMES:
        raise InvalidUrlError("Só são suportados URLs http:// e https://.")
    if not host:
        raise InvalidUrlError("O URL não tem um endereço de servidor.")
    return url


def extract_urls(text: str) -> list[str]:
    """Extrai URLs http(s) válidos de um texto (um ou vários), sem duplicados e pela ordem original."""
    seen: dict[str, None] = {}
    for match in _URL_IN_TEXT.findall(text):
        candidate = match.rstrip(".,;)")
        try:
            seen.setdefault(validate_url(candidate), None)
        except InvalidUrlError:
            continue
    return list(seen)


def redact_url(url: str) -> str:
    """Versão do URL segura para logs: sem credenciais nem query string."""
    try:
        parts = urlsplit(url)
        host = parts.hostname or ""
        netloc = f"{host}:{parts.port}" if parts.port else host
    except ValueError:
        return "<url inválido>"
    return urlunsplit((parts.scheme, netloc, parts.path, "", "")) + ("?…" if parts.query else "")


def filename_from_url(url: str) -> str:
    """Nome de ficheiro sugerido pelo caminho do URL (`download` se não houver)."""
    path = urlsplit(url).path
    name = unquote(path.rsplit("/", 1)[-1]).strip()
    return name or "download"
