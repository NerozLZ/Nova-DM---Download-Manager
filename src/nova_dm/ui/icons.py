"""Ícones SVG desenhados no projeto (grelha 24x24), pintados com a cor pedida."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"

_STROKE = 'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"'

_PATHS: dict[str, str] = {
    "download": '<path d="M12 4v11m0 0l-4.5-4.5M12 15l4.5-4.5M5 19.5h14"/>',
    "progress": '<circle cx="12" cy="12" r="9"/><path d="M12 8v8m0 0l-3-3m3 3l3-3"/>',
    "queue": '<path d="M4 7h16M4 12h16M4 17h10"/>',
    "check": '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    "pause-circle": '<circle cx="12" cy="12" r="9"/><path d="M10 9v6M14 9v6"/>',
    "alert": '<path d="M12 4L2.8 20h18.4z"/><path d="M12 10v4.5M12 17.2v.01"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "settings": '<path d="M4 7h9M17 7h3M4 17h3M11 17h9"/><circle cx="15" cy="7" r="2"/><circle cx="9" cy="17" r="2"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "search": '<circle cx="11" cy="11" r="6.5"/><path d="M16 16l4.5 4.5"/>',
    "play": '<path d="M8 5.5v13l11-6.5z" fill="currentColor"/>',
    "pause": '<path d="M9 6v12M15 6v12" stroke-width="3"/>',
    "dots": '<circle cx="12" cy="5" r="1.7" fill="currentColor"/><circle cx="12" cy="12" r="1.7" fill="currentColor"/><circle cx="12" cy="19" r="1.7" fill="currentColor"/>',
    "folder": '<path d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z"/>',
    "trash": '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 002 2h6a2 2 0 002-2l1-12M9 7V4h6v3"/>',
    "copy": '<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V6a2 2 0 012-2h9"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.6v.01"/>',
    "retry": '<path d="M20 12a8 8 0 11-2.6-5.9"/><path d="M20 4v5h-5"/>',
    "file": '<path d="M14 3H7a2 2 0 00-2 2v14a2 2 0 002 2h10a2 2 0 002-2V8z"/><path d="M14 3v5h5"/>',
    "x-circle": '<circle cx="12" cy="12" r="9"/><path d="M9 9l6 6M15 9l-6 6"/>',
    "x": '<path d="M6 6l12 12M18 6L6 18"/>',
    # glifos das categorias
    "video": '<path d="M8 5.5v13l11-6.5z" fill="currentColor"/>',
    "music": '<path d="M9 18V6l10-2v12"/><circle cx="6.8" cy="18" r="2.4" fill="currentColor"/><circle cx="16.8" cy="16" r="2.4" fill="currentColor"/>',
    "document": '<path d="M7 3.5h7l4 4V20.5H7z"/><path d="M10 12h5M10 15.5h5"/>',
    "image": '<rect x="4" y="5" width="16" height="14" rx="2"/><path d="M4 16l4.5-4.5 3.5 3.5 3-3 5 5"/><circle cx="9" cy="9.5" r="1.3" fill="currentColor"/>',
    "program": '<path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z"/><path d="M12 12l8-4.5M12 12L4 7.5M12 12v9"/>',
    "archive": '<rect x="4" y="4" width="16" height="5" rx="1"/><path d="M5.5 9v10h13V9M10 13h4"/>',
    "other": '<circle cx="12" cy="12" r="2.2" fill="currentColor"/>',
}

# (cor do fundo do ícone, glifo)
CATEGORY_STYLE: dict[str, tuple[str, str]] = {
    "video": ("#7c4dff", "video"),
    "music": ("#e8466f", "music"),
    "document": ("#3b6bff", "document"),
    "image": ("#14b8a6", "image"),
    "program": ("#f97316", "program"),
    "archive": ("#eab308", "archive"),
    "other": ("#64748b", "other"),
}


def _svg(name: str, color: str) -> bytes:
    body = _PATHS[name].replace("currentColor", color)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" {_STROKE.replace("currentColor", color)}>'
        f"{body}</svg>"
    ).encode()


@lru_cache(maxsize=512)
def pixmap(name: str, color: str, size: int, dpr: float = 1.0) -> QPixmap:
    px = QPixmap(int(size * dpr), int(size * dpr))
    px.fill(Qt.GlobalColor.transparent)
    painter = QPainter(px)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    QSvgRenderer(QByteArray(_svg(name, color))).render(painter)
    painter.end()
    px.setDevicePixelRatio(dpr)
    return px


def icon(name: str, color: str, size: int = 22) -> QIcon:
    result = QIcon()
    for dpr in (1.0, 2.0):
        result.addPixmap(pixmap(name, color, size, dpr))
    return result


def logo_icon() -> QIcon:
    return QIcon(str(ASSETS_DIR / "logo.svg"))


def logo_pixmap(size: int, dpr: float = 1.0) -> QPixmap:
    px = QPixmap(int(size * dpr), int(size * dpr))
    px.fill(Qt.GlobalColor.transparent)
    painter = QPainter(px)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    QSvgRenderer(str(ASSETS_DIR / "logo.svg")).render(painter)
    painter.end()
    px.setDevicePixelRatio(dpr)
    return px
