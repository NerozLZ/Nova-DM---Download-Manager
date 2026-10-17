"""Textos e cores usados para apresentar estados e categorias."""

from __future__ import annotations

from nova_dm.core.models import DownloadStatus
from nova_dm.i18n import tr
from nova_dm.ui.styles import Palette


def status_label(status: DownloadStatus) -> str:
    return {
        DownloadStatus.QUEUED: tr("Queued"),
        DownloadStatus.ACTIVE: tr("Downloading"),
        DownloadStatus.PAUSED: tr("Paused"),
        DownloadStatus.COMPLETED: tr("Completed"),
        DownloadStatus.FAILED: tr("Failed"),
        DownloadStatus.CANCELLED: tr("Cancelled"),
    }[status]


def status_color(palette: Palette, status: DownloadStatus) -> str:
    return {
        DownloadStatus.QUEUED: palette.text_muted,
        DownloadStatus.ACTIVE: palette.accent_2,
        DownloadStatus.PAUSED: palette.warning,
        DownloadStatus.COMPLETED: palette.success,
        DownloadStatus.FAILED: palette.danger,
        DownloadStatus.CANCELLED: palette.text_muted,
    }[status]


def progress_color(palette: Palette, status: DownloadStatus) -> str:
    return {
        DownloadStatus.ACTIVE: palette.accent,
        DownloadStatus.QUEUED: palette.text_faint,
        DownloadStatus.PAUSED: palette.warning,
        DownloadStatus.COMPLETED: palette.success,
        DownloadStatus.FAILED: palette.danger,
        DownloadStatus.CANCELLED: palette.text_faint,
    }[status]


def category_label(category: str) -> str:
    return {
        "video": tr("Videos"),
        "music": tr("Music"),
        "document": tr("Documents"),
        "image": tr("Images"),
        "program": tr("Programs"),
        "archive": tr("Archives"),
        "other": tr("Other"),
    }.get(category, tr("Other"))
