"""Esquema SQLite e conversão entre linhas e DownloadRecord."""

from __future__ import annotations

import sqlite3

from nova_dm.core.models import DownloadRecord, DownloadStatus

SCHEMA_VERSION = 2

SCHEMA_V1 = """
CREATE TABLE downloads (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    url             TEXT    NOT NULL,
    filename        TEXT    NOT NULL,
    directory       TEXT    NOT NULL,
    status          TEXT    NOT NULL,
    total_bytes     INTEGER NOT NULL DEFAULT 0,
    completed_bytes INTEGER NOT NULL DEFAULT 0,
    download_speed  INTEGER NOT NULL DEFAULT 0,
    connections     INTEGER NOT NULL DEFAULT 0,
    speed_limit     INTEGER NOT NULL DEFAULT 0,
    gid             TEXT,
    category        TEXT    NOT NULL DEFAULT 'other',
    error_message   TEXT    NOT NULL DEFAULT '',
    created_at      TEXT    NOT NULL,
    completed_at    TEXT
);
CREATE INDEX idx_downloads_status ON downloads(status);

CREATE TABLE settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

SCHEMA_V2 = """
ALTER TABLE downloads ADD COLUMN position INTEGER NOT NULL DEFAULT 0;
UPDATE downloads SET position = id;
"""

COLUMNS = (
    "url",
    "filename",
    "directory",
    "status",
    "total_bytes",
    "completed_bytes",
    "download_speed",
    "connections",
    "speed_limit",
    "gid",
    "category",
    "error_message",
    "created_at",
    "completed_at",
    "position",
)


def migrate(conn: sqlite3.Connection) -> None:
    version = int(conn.execute("PRAGMA user_version").fetchone()[0])
    if version > SCHEMA_VERSION:
        raise RuntimeError(
            f"A base de dados é de uma versão mais recente ({version}) do que esta aplicação suporta ({SCHEMA_VERSION})."
        )
    if version < 1:
        conn.executescript(SCHEMA_V1)
        conn.execute("PRAGMA user_version = 1")
        conn.commit()
        version = 1
    if version < 2:
        conn.executescript(SCHEMA_V2)
        conn.execute("PRAGMA user_version = 2")
        conn.commit()


def record_to_values(record: DownloadRecord) -> tuple[object, ...]:
    return (
        record.url,
        record.filename,
        record.directory,
        record.status.value,
        record.total_bytes,
        record.completed_bytes,
        record.download_speed,
        record.connections,
        record.speed_limit,
        record.gid,
        record.category,
        record.error_message,
        record.created_at,
        record.completed_at,
        record.position,
    )


def row_to_record(row: sqlite3.Row) -> DownloadRecord:
    return DownloadRecord(
        id=int(row["id"]),
        url=row["url"],
        filename=row["filename"],
        directory=row["directory"],
        status=DownloadStatus(row["status"]),
        total_bytes=row["total_bytes"],
        completed_bytes=row["completed_bytes"],
        download_speed=row["download_speed"],
        connections=row["connections"],
        speed_limit=row["speed_limit"],
        gid=row["gid"],
        category=row["category"],
        error_message=row["error_message"],
        created_at=row["created_at"],
        completed_at=row["completed_at"],
        position=row["position"],
    )
