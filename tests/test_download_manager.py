"""Testes de integração: DownloadManager + aria2c real + servidor HTTP local."""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from pathlib import Path

import pytest

from nova_dm.core.aria2_engine import Aria2Engine
from nova_dm.core.download_manager import DownloadManager
from nova_dm.core.models import DownloadRecord, DownloadStatus
from nova_dm.database.repository import Repository
from nova_dm.errors import EngineUnavailableError, NovaDMError
from tests.conftest import needs_aria2
from tests.http_server import TestServer, make_payload

pytestmark = [pytest.mark.integration, needs_aria2]


def wait_for(manager: DownloadManager, download_id: int, predicate: Callable[[DownloadRecord], bool], timeout: float = 30.0) -> DownloadRecord:
    deadline = time.monotonic() + timeout
    last: DownloadRecord | None = None
    while time.monotonic() < deadline:
        for record in manager.poll():
            if record.id == download_id:
                last = record
                if predicate(record):
                    return record
        time.sleep(0.1)
    raise AssertionError(f"Tempo esgotado; último estado: {last}")


def test_download_completes_with_correct_content(manager: DownloadManager, downloads_dir: Path) -> None:
    payload = make_payload(3 * 1024 * 1024)
    with TestServer() as server:
        server.files["data.bin"] = payload
        record = manager.add(server.url("data.bin"), downloads_dir, "data.bin", connections=4)
        done = wait_for(manager, record.id, lambda r: r.status is DownloadStatus.COMPLETED)
    assert hashlib.sha256((downloads_dir / "data.bin").read_bytes()).hexdigest() == hashlib.sha256(payload).hexdigest()
    assert done.total_bytes == len(payload)
    assert done.progress == 1.0
    assert done.completed_at is not None
    assert done.gid is None
    assert not (downloads_dir / "data.bin.aria2").exists()


def test_segmented_download_uses_several_connections(manager: DownloadManager, downloads_dir: Path) -> None:
    payload = make_payload(4 * 1024 * 1024)
    with TestServer(delay=0.01, chunk_size=16384) as server:
        server.files["big.bin"] = payload
        record = manager.add(server.url("big.bin"), downloads_dir, "big.bin", connections=4)
        wait_for(manager, record.id, lambda r: r.status is DownloadStatus.COMPLETED, timeout=60)
        ranged = [req for req in server.requests if req[0] == "GET" and req[2]]
    assert len(ranged) >= 2, "esperava-se mais do que um pedido com Range (transferência segmentada)"
    assert (downloads_dir / "big.bin").read_bytes() == payload


def test_pause_resume_and_progress(manager: DownloadManager, downloads_dir: Path) -> None:
    payload = make_payload(2 * 1024 * 1024)
    with TestServer(delay=0.02, chunk_size=8192) as server:
        server.files["slow.bin"] = payload
        record = manager.add(server.url("slow.bin"), downloads_dir, "slow.bin", connections=2)
        active = wait_for(manager, record.id, lambda r: r.status is DownloadStatus.ACTIVE and r.completed_bytes > 0)
        assert active.download_speed > 0

        manager.pause(record.id)
        paused = wait_for(manager, record.id, lambda r: r.status is DownloadStatus.PAUSED)
        frozen = paused.completed_bytes
        time.sleep(0.6)
        assert next(r for r in manager.poll() if r.id == record.id).completed_bytes - frozen < 128 * 1024

        manager.resume(record.id)
        wait_for(manager, record.id, lambda r: r.status is DownloadStatus.COMPLETED, timeout=60)
    assert (downloads_dir / "slow.bin").read_bytes() == payload


def test_cancel_deletes_partial_files_but_keeps_record(manager: DownloadManager, downloads_dir: Path) -> None:
    with TestServer(delay=0.05, chunk_size=4096) as server:
        server.files["x.bin"] = make_payload(2 * 1024 * 1024)
        record = manager.add(server.url("x.bin"), downloads_dir, "x.bin", connections=2)
        wait_for(manager, record.id, lambda r: r.status is DownloadStatus.ACTIVE and r.completed_bytes > 0)
        manager.cancel(record.id)
    assert not (downloads_dir / "x.bin").exists()
    assert not (downloads_dir / "x.bin.aria2").exists()
    after = next(r for r in manager.poll() if r.id == record.id)
    assert after.status is DownloadStatus.CANCELLED
    assert after.completed_bytes == 0


def test_retry_after_cancel_completes(manager: DownloadManager, downloads_dir: Path) -> None:
    payload = make_payload(512 * 1024)
    with TestServer(delay=0.05, chunk_size=4096) as server:
        server.files["r.bin"] = payload
        record = manager.add(server.url("r.bin"), downloads_dir, "r.bin", connections=1)
        wait_for(manager, record.id, lambda r: r.status is DownloadStatus.ACTIVE)
        manager.cancel(record.id)
        server.delay = 0
        manager.retry(record.id)
        wait_for(manager, record.id, lambda r: r.status is DownloadStatus.COMPLETED)
    assert (downloads_dir / "r.bin").read_bytes() == payload


def test_http_404_marks_failed_and_retry_after_fix(manager: DownloadManager, downloads_dir: Path) -> None:
    with TestServer() as server:
        record = manager.add(server.url("missing.bin"), downloads_dir, "missing.bin", connections=1)
        failed = wait_for(manager, record.id, lambda r: r.status is DownloadStatus.FAILED)
        assert "404" in failed.error_message or failed.error_message
        assert failed.gid is None

        server.files["missing.bin"] = make_payload(1000)
        manager.retry(record.id)
        wait_for(manager, record.id, lambda r: r.status is DownloadStatus.COMPLETED)
    assert (downloads_dir / "missing.bin").stat().st_size == 1000


def test_connection_refused_marks_failed(manager: DownloadManager, downloads_dir: Path) -> None:
    record = manager.add("http://127.0.0.1:1/never.bin", downloads_dir, "never.bin", connections=1)
    failed = wait_for(manager, record.id, lambda r: r.status is DownloadStatus.FAILED, timeout=60)
    assert failed.error_message


def test_remove_keeps_file_and_delete_removes_it(manager: DownloadManager, downloads_dir: Path) -> None:
    with TestServer() as server:
        server.files["a.bin"] = make_payload(10_000)
        server.files["b.bin"] = make_payload(10_000, seed=3)
        a = manager.add(server.url("a.bin"), downloads_dir, "a.bin", connections=1)
        b = manager.add(server.url("b.bin"), downloads_dir, "b.bin", connections=1)
        wait_for(manager, a.id, lambda r: r.status is DownloadStatus.COMPLETED)
        wait_for(manager, b.id, lambda r: r.status is DownloadStatus.COMPLETED)

    manager.remove(a.id)
    manager.remove(b.id, delete_files=True)
    assert (downloads_dir / "a.bin").exists()
    assert not (downloads_dir / "b.bin").exists()
    assert manager.records() == []


def test_actions_validate_state(manager: DownloadManager, downloads_dir: Path) -> None:
    with TestServer() as server:
        server.files["a.bin"] = make_payload(1000)
        record = manager.add(server.url("a.bin"), downloads_dir, "a.bin", connections=1)
        wait_for(manager, record.id, lambda r: r.status is DownloadStatus.COMPLETED)
    for action in (manager.pause, manager.resume, manager.cancel, manager.retry):
        with pytest.raises(NovaDMError):
            action(record.id)
    with pytest.raises(NovaDMError):
        manager.pause(9999)


def test_add_paused_does_not_download_until_resumed(manager: DownloadManager, downloads_dir: Path) -> None:
    with TestServer() as server:
        server.files["p.bin"] = make_payload(50_000)
        record = manager.add(server.url("p.bin"), downloads_dir, "p.bin", connections=1, start=False)
        wait_for(manager, record.id, lambda r: r.status is DownloadStatus.PAUSED)
        time.sleep(0.5)
        assert not any(req[0] == "GET" for req in server.requests)
        manager.resume(record.id)
        wait_for(manager, record.id, lambda r: r.status is DownloadStatus.COMPLETED)


def test_max_concurrent_limits_active_transfers(manager: DownloadManager, downloads_dir: Path) -> None:
    manager.set_global_options(max_concurrent=1, download_limit=0)
    with TestServer(delay=0.05, chunk_size=4096) as server:
        ids = []
        for i in range(3):
            server.files[f"q{i}.bin"] = make_payload(400_000, seed=i)
            ids.append(manager.add(server.url(f"q{i}.bin"), downloads_dir, f"q{i}.bin", connections=1).id)
        time.sleep(1.0)
        statuses = [r.status for r in manager.poll()]
        assert statuses.count(DownloadStatus.ACTIVE) == 1
        assert statuses.count(DownloadStatus.QUEUED) == 2
        for i in ids:
            manager.cancel(i)


def test_global_speed_limit_is_applied(manager: DownloadManager, downloads_dir: Path) -> None:
    limit = 100 * 1024
    manager.set_global_options(max_concurrent=3, download_limit=limit)
    with TestServer() as server:
        server.files["lim.bin"] = make_payload(2 * 1024 * 1024)
        record = manager.add(server.url("lim.bin"), downloads_dir, "lim.bin", connections=1)
        wait_for(manager, record.id, lambda r: r.status is DownloadStatus.ACTIVE and r.download_speed > 0)
        time.sleep(2.5)  # o aria2 deixa passar um pequeno pico inicial; mede-se depois de estabilizar
        sample = next(r for r in manager.poll() if r.id == record.id)
        manager.cancel(record.id)
    assert sample.download_speed <= limit * 1.5
    # Sem limite, 2 MB em localhost terminariam em milissegundos.
    assert sample.completed_bytes < 1024 * 1024


def test_restart_resumes_partial_download(repo: Repository, downloads_dir: Path) -> None:
    """Simula fechar a aplicação a meio de uma transferência e voltar a abri-la."""
    payload = make_payload(2 * 1024 * 1024)
    with TestServer(delay=0.02, chunk_size=8192) as server:
        server.files["resume.bin"] = payload

        engine1 = Aria2Engine()
        engine1.start()
        first = DownloadManager(engine1, repo)
        first.startup()
        record = first.add(server.url("resume.bin"), downloads_dir, "resume.bin", connections=1)
        partial = wait_for(first, record.id, lambda r: r.status is DownloadStatus.ACTIVE and r.completed_bytes > 200_000)
        first.shutdown()  # fecha a aplicação
        stored = repo.get(record.id)
        assert stored is not None and stored.status is DownloadStatus.ACTIVE
        assert partial.completed_bytes < len(payload)

        server.delay = 0
        server.requests.clear()
        engine2 = Aria2Engine()
        engine2.start()
        second = DownloadManager(engine2, repo, auto_resume=True)
        try:
            second.startup()
            wait_for(second, record.id, lambda r: r.status is DownloadStatus.COMPLETED, timeout=60)
        finally:
            engine2.stop()
        resumed_requests = [req for req in server.requests if req[0] == "GET" and req[2]]
    assert (downloads_dir / "resume.bin").read_bytes() == payload
    assert resumed_requests, "a retoma devia usar pedidos com Range, em vez de recomeçar do zero"


def test_restart_without_auto_resume_leaves_paused(repo: Repository, downloads_dir: Path) -> None:
    with TestServer(delay=0.05, chunk_size=4096) as server:
        server.files["hold.bin"] = make_payload(1024 * 1024)
        engine1 = Aria2Engine()
        engine1.start()
        first = DownloadManager(engine1, repo)
        first.startup()
        record = first.add(server.url("hold.bin"), downloads_dir, "hold.bin", connections=1)
        wait_for(first, record.id, lambda r: r.status is DownloadStatus.ACTIVE and r.completed_bytes > 0)
        first.shutdown()

        server.requests.clear()
        engine2 = Aria2Engine()
        engine2.start()
        second = DownloadManager(engine2, repo, auto_resume=False)
        try:
            second.startup()
            state = wait_for(second, record.id, lambda r: r.status is DownloadStatus.PAUSED)
            time.sleep(0.5)
            assert not any(req[0] == "GET" for req in server.requests)
            assert state.completed_bytes >= 0
            second.resume(record.id)
            server.delay = 0
            wait_for(second, record.id, lambda r: r.status is DownloadStatus.COMPLETED, timeout=60)
        finally:
            engine2.stop()


def test_reconcile_detects_file_already_complete(repo: Repository, downloads_dir: Path) -> None:
    """A BD diz «em curso», mas o ficheiro já está completo no disco (ex.: falha antes de gravar)."""
    payload = make_payload(5000)
    (downloads_dir / "done.bin").write_bytes(payload)
    record = repo.add(
        DownloadRecord(
            url="http://127.0.0.1:1/done.bin", filename="done.bin", directory=str(downloads_dir),
            status=DownloadStatus.ACTIVE, total_bytes=len(payload), completed_bytes=4000, gid="old",
        )
    )
    engine = Aria2Engine()
    engine.start()
    try:
        manager = DownloadManager(engine, repo)
        manager.startup()
        loaded = manager.get(record.id)
    finally:
        engine.stop()
    assert loaded.status is DownloadStatus.COMPLETED
    assert loaded.completed_bytes == len(payload)
    assert loaded.gid is None


def test_engine_unavailable_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", "/nonexistent")
    with pytest.raises(EngineUnavailableError):
        Aria2Engine().start()


def test_no_orphan_aria2_process_after_stop() -> None:
    engine = Aria2Engine()
    engine.start()
    process = engine._process  # noqa: SLF001
    assert process is not None and process._proc is not None  # noqa: SLF001
    pid = process._proc.pid  # noqa: SLF001
    engine.stop()
    assert not engine.is_running
    with pytest.raises(ProcessLookupError):
        import os

        os.kill(pid, 0)
