from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from nova_dm.config import Settings
from nova_dm.core.models import DownloadRecord, DownloadStatus
from nova_dm.database.models import SCHEMA_VERSION
from nova_dm.database.repository import Repository


def make_record(**overrides: object) -> DownloadRecord:
    data: dict[str, object] = {"url": "https://a.com/f.zip", "filename": "f.zip", "directory": "/tmp/d"}
    data.update(overrides)
    return DownloadRecord(**data)  # type: ignore[arg-type]


def test_add_get_save_delete(repo: Repository) -> None:
    record = repo.add(make_record())
    assert record.id is not None
    loaded = repo.get(record.id)
    assert loaded is not None
    assert loaded.url == "https://a.com/f.zip"
    assert loaded.status is DownloadStatus.QUEUED

    record.status = DownloadStatus.COMPLETED
    record.total_bytes = 100
    record.completed_bytes = 100
    record.completed_at = "2026-10-16T02:00:00+00:00"
    repo.save(record)
    again = repo.get(record.id)
    assert again is not None
    assert again.status is DownloadStatus.COMPLETED
    assert again.total_bytes == 100
    assert again.progress == 1.0

    repo.delete(record.id)
    assert repo.get(record.id) is None


def test_list_is_ordered_by_id(repo: Repository) -> None:
    for name in ("a", "b", "c"):
        repo.add(make_record(filename=name))
    assert [r.filename for r in repo.list_downloads()] == ["a", "b", "c"]


def test_save_requires_inserted_record(repo: Repository) -> None:
    with pytest.raises(ValueError):
        repo.save(make_record())


def test_settings_roundtrip_and_defaults(repo: Repository) -> None:
    assert repo.get_setting("nada", 5) == 5
    repo.set_setting("theme", "light")
    repo.set_setting("theme", "dark")
    assert repo.get_setting("theme") == "dark"
    assert repo.all_settings() == {"theme": "dark"}


def test_settings_dataclass_persistence_and_clamping(repo: Repository) -> None:
    Settings(download_dir="/x", max_concurrent=99, connections_per_download=0, theme="neon").save(repo)
    loaded = Settings.load(repo)
    assert loaded.download_dir == "/x"
    assert loaded.max_concurrent == 20
    assert loaded.connections_per_download == 1
    assert loaded.theme == "dark"


def test_corrupt_setting_falls_back_to_default(repo: Repository) -> None:
    repo._conn.execute("INSERT INTO settings (key, value) VALUES ('max_concurrent', '{não é json')")
    assert Settings.load(repo, "/dl").max_concurrent == 3


def test_persists_across_connections(tmp_path: Path) -> None:
    db = tmp_path / "x" / "db.sqlite3"
    first = Repository(db)
    first.add(make_record(filename="persistente"))
    first.close()
    second = Repository(db)
    assert [r.filename for r in second.list_downloads()] == ["persistente"]
    second.close()


def test_refuses_newer_schema(tmp_path: Path) -> None:
    db = tmp_path / "future.sqlite3"
    conn = sqlite3.connect(db)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
    conn.close()
    with pytest.raises(RuntimeError):
        Repository(db)
