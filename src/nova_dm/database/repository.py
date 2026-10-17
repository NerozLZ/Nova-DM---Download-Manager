"""Acesso à base de dados SQLite (downloads e definições)."""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from pathlib import Path
from typing import Any

from nova_dm.core.models import DownloadRecord
from nova_dm.database.models import COLUMNS, migrate, record_to_values, row_to_record

log = logging.getLogger(__name__)


class Repository:
    """Repositório thread-safe (uma ligação protegida por um lock)."""

    def __init__(self, path: Path | str) -> None:
        self._lock = threading.RLock()
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            if str(path) != ":memory:":
                self._conn.execute("PRAGMA journal_mode = WAL")
            self._conn.execute("PRAGMA foreign_keys = ON")
            migrate(self._conn)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # Downloads -------------------------------------------------------

    def add(self, record: DownloadRecord) -> DownloadRecord:
        placeholders = ", ".join("?" for _ in COLUMNS)
        with self._lock, self._conn:
            if record.position <= 0:
                record.position = int(self._conn.execute("SELECT COALESCE(MAX(position), 0) + 1 FROM downloads").fetchone()[0])
            cursor = self._conn.execute(
                f"INSERT INTO downloads ({', '.join(COLUMNS)}) VALUES ({placeholders})",
                record_to_values(record),
            )
        record.id = int(cursor.lastrowid or 0)
        return record

    def save(self, record: DownloadRecord) -> None:
        if record.id is None:
            raise ValueError("Só é possível guardar registos já inseridos.")
        assignments = ", ".join(f"{col} = ?" for col in COLUMNS)
        with self._lock, self._conn:
            self._conn.execute(
                f"UPDATE downloads SET {assignments} WHERE id = ?",
                (*record_to_values(record), record.id),
            )

    def get(self, download_id: int) -> DownloadRecord | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM downloads WHERE id = ?", (download_id,)).fetchone()
        return row_to_record(row) if row else None

    def list_downloads(self) -> list[DownloadRecord]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM downloads ORDER BY position, id").fetchall()
        return [row_to_record(row) for row in rows]

    def delete(self, download_id: int) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM downloads WHERE id = ?", (download_id,))

    # Definições ------------------------------------------------------

    def get_setting(self, key: str, default: Any = None) -> Any:
        with self._lock:
            row = self._conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        if row is None:
            return default
        try:
            return json.loads(row["value"])
        except json.JSONDecodeError:
            log.warning("Definição %r com valor inválido na base de dados; a usar o valor por omissão", key)
            return default

    def set_setting(self, key: str, value: Any) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, json.dumps(value)),
            )

    def all_settings(self) -> dict[str, Any]:
        with self._lock:
            rows = self._conn.execute("SELECT key, value FROM settings").fetchall()
        result: dict[str, Any] = {}
        for row in rows:
            try:
                result[row["key"]] = json.loads(row["value"])
            except json.JSONDecodeError:
                log.warning("Definição %r ignorada: valor inválido", row["key"])
        return result
