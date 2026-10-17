"""Operações seguras sobre ficheiros e pastas de destino."""

from __future__ import annotations

import logging
import os
import shutil
import unicodedata
from collections.abc import Iterable
from pathlib import Path

from nova_dm.errors import InsufficientSpaceError, InvalidDestinationError

log = logging.getLogger(__name__)

CONTROL_SUFFIX = ".aria2"
_MAX_NAME_BYTES = 200  # margem para o sufixo ".aria2" e para " (n)"

CATEGORY_EXTENSIONS: dict[str, tuple[str, ...]] = {
    "video": ("mp4", "mkv", "avi", "mov", "webm", "flv", "wmv", "m4v", "mpg", "mpeg", "ts"),
    "music": ("mp3", "flac", "wav", "ogg", "opus", "m4a", "aac", "wma"),
    "document": ("pdf", "doc", "docx", "odt", "txt", "epub", "xls", "xlsx", "ods", "ppt", "pptx", "odp", "csv", "md"),
    "image": ("jpg", "jpeg", "png", "gif", "webp", "svg", "bmp", "tif", "tiff", "heic", "avif"),
    "program": ("exe", "msi", "deb", "rpm", "appimage", "flatpak", "apk", "run", "sh", "bin"),
    "archive": ("zip", "rar", "7z", "tar", "gz", "bz2", "xz", "zst", "iso", "img"),
}
CATEGORIES = (*CATEGORY_EXTENSIONS, "other")


def category_for(filename: str) -> str:
    suffix = Path(filename).suffix.lstrip(".").lower()
    for category, extensions in CATEGORY_EXTENSIONS.items():
        if suffix in extensions:
            return category
    return "other"


def sanitize_filename(name: str) -> str:
    """Remove separadores de caminho, caracteres de controlo e nomes perigosos."""
    cleaned = unicodedata.normalize("NFC", name)
    cleaned = "".join(ch for ch in cleaned if ch.isprintable() and ch not in '/\\\0')
    cleaned = cleaned.strip().strip(".")
    while len(cleaned.encode("utf-8")) > _MAX_NAME_BYTES:
        cleaned = _shorten(cleaned)
    return cleaned or "download"


def _shorten(name: str) -> str:
    stem, dot, ext = name.rpartition(".")
    if dot and 0 < len(ext) <= 10 and stem:
        return stem[:-1] + "." + ext
    return name[:-1]


def validate_directory(directory: str | Path) -> Path:
    """Garante que a pasta é absoluta, existe (ou pode ser criada) e é gravável."""
    path = Path(directory).expanduser()
    if not path.is_absolute():
        raise InvalidDestinationError("A pasta de destino tem de ser um caminho absoluto.")
    path = Path(os.path.normpath(path))
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise InvalidDestinationError(f"Não foi possível criar a pasta de destino: {exc.strerror or exc}") from exc
    if not path.is_dir():
        raise InvalidDestinationError("O destino indicado não é uma pasta.")
    if not os.access(path, os.W_OK | os.X_OK):
        raise InvalidDestinationError("Não tem permissão para escrever na pasta de destino.")
    return path


def resolve_target(directory: Path, filename: str) -> Path:
    """Caminho final do ficheiro, garantindo que fica dentro da pasta de destino."""
    target = (directory / filename).resolve()
    if target.parent != directory.resolve():
        raise InvalidDestinationError("O nome do ficheiro sai da pasta de destino.")
    return target


def unique_filename(directory: Path, filename: str, reserved: Iterable[str] = ()) -> str:
    """Primeiro nome livre (`nome.ext`, `nome (1).ext`, ...) para evitar sobrescritas."""
    taken = set(reserved)

    def is_free(candidate: str) -> bool:
        path = directory / candidate
        return candidate not in taken and not path.exists() and not (directory / (candidate + CONTROL_SUFFIX)).exists()

    if is_free(filename):
        return filename
    stem, dot, ext = filename.rpartition(".")
    if not dot or not stem:
        stem, ext = filename, ""
    else:
        ext = "." + ext
    counter = 1
    while True:
        candidate = f"{stem} ({counter}){ext}"
        if is_free(candidate):
            return candidate
        counter += 1


def check_free_space(directory: Path, needed_bytes: int) -> None:
    if needed_bytes <= 0:
        return
    free = shutil.disk_usage(directory).free
    if free < needed_bytes:
        raise InsufficientSpaceError(
            f"Espaço insuficiente em {directory}: são necessários {needed_bytes} bytes e há {free} livres."
        )


def delete_download_files(directory: str | Path, filename: str) -> list[Path]:
    """Apaga o ficheiro descarregado (ou parcial) e o respetivo ficheiro de controlo do aria2.

    Só atua dentro de `directory`. Devolve os ficheiros removidos.
    """
    target = resolve_target(Path(directory), filename)
    removed: list[Path] = []
    for path in (target, target.with_name(target.name + CONTROL_SUFFIX)):
        try:
            path.unlink()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise InvalidDestinationError(f"Não foi possível apagar {path.name}: {exc.strerror or exc}") from exc
        removed.append(path)
    return removed
