"""Caminhos da aplicação e definições do utilizador."""

from __future__ import annotations

import os
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any

from nova_dm.database.repository import Repository

MIN_CONNECTIONS, MAX_CONNECTIONS = 1, 16
BROWSER_PORT_DEFAULT = 17650
BROWSER_PORT_MIN = 1024
BROWSER_PORT_MAX = 65535
MAX_CONCURRENT_LIMIT = 20
THEMES = ("dark", "light")


def _xdg(variable: str, fallback: str) -> Path:
    value = os.environ.get(variable, "")
    return Path(value) if value.startswith("/") else Path.home() / fallback


@dataclass(frozen=True, slots=True)
class AppPaths:
    config_dir: Path
    data_dir: Path
    log_dir: Path

    @classmethod
    def default(cls) -> AppPaths:
        data = _xdg("XDG_DATA_HOME", ".local/share") / "nova-dm"
        return cls(
            config_dir=_xdg("XDG_CONFIG_HOME", ".config") / "nova-dm",
            data_dir=data,
            log_dir=_xdg("XDG_STATE_HOME", ".local/state") / "nova-dm",
        )

    @classmethod
    def under(cls, root: Path) -> AppPaths:
        """Todos os caminhos dentro de `root` (útil em testes)."""
        return cls(root / "config", root / "data", root / "logs")

    @property
    def database_file(self) -> Path:
        return self.data_dir / "nova_dm.sqlite3"

    @property
    def aria2_log_file(self) -> Path:
        return self.log_dir / "aria2.log"

    def ensure(self) -> None:
        for directory in (self.config_dir, self.data_dir, self.log_dir):
            directory.mkdir(parents=True, exist_ok=True)


def default_download_dir() -> str:
    return str(_xdg("XDG_DOWNLOAD_DIR", "Downloads"))


@dataclass(slots=True)
class Settings:
    download_dir: str = ""
    max_concurrent: int = 3
    connections_per_download: int = 4
    global_speed_limit_kib: int = 0  # 0 = sem limite
    theme: str = "dark"
    language: str = "system"
    confirm_delete: bool = True
    auto_resume: bool = True
    aria2_path: str = ""
    browser_integration: bool = False
    browser_port: int = BROWSER_PORT_DEFAULT
    browser_token: str = ""
    browser_confirm: bool = True  # perguntar antes de adicionar os links vindos do navegador

    def normalized(self) -> Settings:
        """Cópia com valores dentro dos limites suportados."""
        return Settings(
            download_dir=self.download_dir.strip(),
            max_concurrent=min(max(1, int(self.max_concurrent)), MAX_CONCURRENT_LIMIT),
            connections_per_download=min(max(MIN_CONNECTIONS, int(self.connections_per_download)), MAX_CONNECTIONS),
            global_speed_limit_kib=max(0, int(self.global_speed_limit_kib)),
            theme=self.theme if self.theme in THEMES else "dark",
            language=self.language or "system",
            confirm_delete=bool(self.confirm_delete),
            auto_resume=bool(self.auto_resume),
            aria2_path=self.aria2_path.strip(),
            browser_integration=bool(self.browser_integration),
            browser_port=min(max(BROWSER_PORT_MIN, int(self.browser_port)), BROWSER_PORT_MAX),
            browser_token=self.browser_token.strip(),
            browser_confirm=bool(self.browser_confirm),
        )

    @property
    def global_speed_limit_bytes(self) -> int:
        return self.global_speed_limit_kib * 1024

    @classmethod
    def load(cls, repository: Repository, fallback_download_dir: str = "") -> Settings:
        stored: dict[str, Any] = repository.all_settings()
        defaults = cls(download_dir=fallback_download_dir or default_download_dir())
        values = {}
        for field in fields(cls):
            raw = stored.get(field.name, getattr(defaults, field.name))
            try:
                values[field.name] = type(getattr(defaults, field.name))(raw)
            except (TypeError, ValueError):
                values[field.name] = getattr(defaults, field.name)
        return cls(**values).normalized()

    def save(self, repository: Repository) -> None:
        for field in fields(self):
            repository.set_setting(field.name, getattr(self, field.name))
