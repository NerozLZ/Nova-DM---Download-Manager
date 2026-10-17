"""Formatação de tamanhos, velocidades e tempos para apresentação."""

from __future__ import annotations

_UNITS = ("B", "KB", "MB", "GB", "TB")


def format_size(num_bytes: int) -> str:
    """Formata um número de bytes (ex.: ``2.45 GB``)."""
    value = float(max(0, num_bytes))
    for unit in _UNITS:
        if value < 1024 or unit == _UNITS[-1]:
            return f"{int(value)} {unit}" if unit == "B" else f"{value:.2f} {unit}"
        value /= 1024
    raise AssertionError("inalcançável")


def format_speed(bytes_per_second: int) -> str:
    return f"{format_size(bytes_per_second)}/s"


def format_eta(seconds: int | None) -> str:
    """Formata segundos como ``HH:MM:SS``; ``—`` se desconhecido."""
    if seconds is None or seconds < 0:
        return "—"
    hours, rest = divmod(int(seconds), 3600)
    minutes, secs = divmod(rest, 60)
    if hours > 99:
        return "—"
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"
