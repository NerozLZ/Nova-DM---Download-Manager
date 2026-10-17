"""Ordem escolhida pelo utilizador: persistência, movimentos e prioridade real na fila do aria2."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from nova_dm.core.download_manager import DownloadManager
from nova_dm.database.models import SCHEMA_V1
from nova_dm.database.repository import Repository
from tests.conftest import needs_aria2

URL = "http://127.0.0.1:9/x"  # nunca é contactado: os downloads são adicionados em pausa


def _order(manager: DownloadManager) -> list[str]:
    return [r.filename for r in manager.records()]


@pytest.fixture
def four(manager: DownloadManager, downloads_dir: Path) -> DownloadManager:
    for name in "abcd":
        manager.add(f"{URL}/{name}", downloads_dir, name, connections=1, start=False)
    return manager


@needs_aria2
def test_new_downloads_go_to_the_end(four: DownloadManager) -> None:
    assert _order(four) == ["a", "b", "c", "d"]


@needs_aria2
@pytest.mark.parametrize(
    ("chosen", "where", "expected"),
    [
        ("c", "top", ["c", "a", "b", "d"]),
        ("b", "bottom", ["a", "c", "d", "b"]),
        ("c", "up", ["a", "c", "b", "d"]),
        ("b", "down", ["a", "c", "b", "d"]),
        ("a", "up", ["a", "b", "c", "d"]),
        ("d", "down", ["a", "b", "c", "d"]),
        ("bc", "up", ["b", "c", "a", "d"]),
        ("ac", "down", ["b", "a", "d", "c"]),
        ("bd", "top", ["b", "d", "a", "c"]),
    ],
)
def test_move(four: DownloadManager, chosen: str, where: str, expected: list[str]) -> None:
    ids = [r.id for r in four.records() if r.filename in chosen]
    four.move(ids, where)
    assert _order(four) == expected


@needs_aria2
@pytest.mark.parametrize(
    ("chosen", "target", "after", "expected"),
    [
        ("d", "a", False, ["d", "a", "b", "c"]),
        ("a", "c", True, ["b", "c", "a", "d"]),
        ("ab", "d", True, ["c", "d", "a", "b"]),
        ("a", None, False, ["b", "c", "d", "a"]),
        ("a", "a", False, ["a", "b", "c", "d"]),
    ],
)
def test_move_to(four: DownloadManager, chosen: str, target: str | None, after: bool, expected: list[str]) -> None:
    by_name = {r.filename: r.id for r in four.records()}
    four.move_to([by_name[c] for c in chosen], by_name[target] if target else None, after=after)
    assert _order(four) == expected


@needs_aria2
def test_order_is_persisted(four: DownloadManager, repo: Repository) -> None:
    four.move([r.id for r in four.records() if r.filename == "d"], "top")
    assert [r.filename for r in repo.list_downloads()] == ["d", "a", "b", "c"]


@needs_aria2
def test_order_reaches_the_aria2_queue(four: DownloadManager, engine) -> None:
    four.move([r.id for r in four.records() if r.filename == "c"], "top")
    gids = {r.id: r.gid for r in four.records()}
    expected = [gids[r.id] for r in four.records()]
    assert [s.gid for s in engine.snapshot()] == expected


def test_migration_from_v1_keeps_order(tmp_path: Path) -> None:
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA_V1)
    conn.execute("PRAGMA user_version = 1")
    for name in ("x", "y"):
        conn.execute(
            "INSERT INTO downloads (url, filename, directory, status, created_at) VALUES (?, ?, '/tmp', 'completed', 't')",
            (f"http://h/{name}", name),
        )
    conn.commit()
    conn.close()
    repo = Repository(path)
    assert [(r.filename, r.position) for r in repo.list_downloads()] == [("x", 1), ("y", 2)]
    repo.close()
