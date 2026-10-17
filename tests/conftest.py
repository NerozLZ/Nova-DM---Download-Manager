from __future__ import annotations

import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest

from nova_dm.core.aria2_engine import Aria2Engine
from nova_dm.core.download_manager import DownloadManager
from nova_dm.database.repository import Repository

needs_aria2 = pytest.mark.skipif(shutil.which("aria2c") is None, reason="aria2c não está instalado")


@pytest.fixture
def repo() -> Iterator[Repository]:
    repository = Repository(":memory:")
    yield repository
    repository.close()


@pytest.fixture
def downloads_dir(tmp_path: Path) -> Path:
    path = tmp_path / "downloads"
    path.mkdir()
    return path


@pytest.fixture
def engine() -> Iterator[Aria2Engine]:
    instance = Aria2Engine()
    instance.start()
    yield instance
    instance.stop()


@pytest.fixture
def manager(engine: Aria2Engine, repo: Repository) -> Iterator[DownloadManager]:
    mgr = DownloadManager(engine, repo)
    mgr.startup()
    yield mgr
