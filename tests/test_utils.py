from __future__ import annotations

import logging
import os
from pathlib import Path

import pytest

from nova_dm.errors import InsufficientSpaceError, InvalidDestinationError, InvalidUrlError
from nova_dm.utils import files
from nova_dm.utils.formatting import format_eta, format_size, format_speed
from nova_dm.utils.logging_setup import RedactingFilter, redact
from nova_dm.utils.urls import extract_urls, filename_from_url, redact_url, validate_url


class TestUrls:
    @pytest.mark.parametrize("url", ["http://a.com/x", "https://a.com:8080/x?y=1", "https://u:p@host/f.zip"])
    def test_valid(self, url: str) -> None:
        assert validate_url(url) == url

    @pytest.mark.parametrize(
        "url", ["", "   ", "ftp://a.com/x", "javascript:alert(1)", "file:///etc/passwd", "http://", "http://a b.com", "https://a.com:99999/"]
    )
    def test_invalid(self, url: str) -> None:
        with pytest.raises(InvalidUrlError):
            validate_url(url)

    def test_extract_urls_dedup_and_order(self) -> None:
        text = "veja https://a.com/1.zip, e\nhttp://b.org/x.iso depois https://a.com/1.zip ftp://x.com/y lixo"
        assert extract_urls(text) == ["https://a.com/1.zip", "http://b.org/x.iso"]

    def test_redact_url_hides_credentials_and_query(self) -> None:
        assert redact_url("https://user:secret@host.com:8443/a/b.zip?token=abc") == "https://host.com:8443/a/b.zip?…"

    def test_filename_from_url(self) -> None:
        assert filename_from_url("https://a.com/dir/My%20File.zip?x=1") == "My File.zip"
        assert filename_from_url("https://a.com/") == "download"


class TestFiles:
    def test_sanitize_removes_separators_and_dots(self) -> None:
        assert files.sanitize_filename("../../etc/passwd") == "etcpasswd"
        assert files.sanitize_filename("..") == "download"
        assert files.sanitize_filename("a\x00b\nc.txt") == "abc.txt"
        assert files.sanitize_filename("") == "download"

    def test_sanitize_limits_length_keeping_extension(self) -> None:
        name = files.sanitize_filename("a" * 400 + ".mp4")
        assert name.endswith(".mp4")
        assert len(name.encode()) <= 200

    def test_resolve_target_blocks_traversal(self, tmp_path: Path) -> None:
        with pytest.raises(InvalidDestinationError):
            files.resolve_target(tmp_path, "../outside.txt")
        assert files.resolve_target(tmp_path, "ok.txt") == tmp_path.resolve() / "ok.txt"

    def test_unique_filename_avoids_existing_partial_and_reserved(self, tmp_path: Path) -> None:
        (tmp_path / "a.zip").write_bytes(b"x")
        (tmp_path / "a (1).zip.aria2").write_bytes(b"x")
        assert files.unique_filename(tmp_path, "a.zip", reserved={"a (2).zip"}) == "a (3).zip"
        assert files.unique_filename(tmp_path, "novo.zip") == "novo.zip"
        assert files.unique_filename(tmp_path, "semext") == "semext"

    def test_validate_directory_requires_absolute_and_creates(self, tmp_path: Path) -> None:
        with pytest.raises(InvalidDestinationError):
            files.validate_directory("relativo/pasta")
        created = files.validate_directory(tmp_path / "novo" / "sub")
        assert created.is_dir()

    def test_validate_directory_rejects_file(self, tmp_path: Path) -> None:
        file = tmp_path / "f"
        file.write_text("x")
        with pytest.raises(InvalidDestinationError):
            files.validate_directory(file)

    @pytest.mark.skipif(os.geteuid() == 0, reason="root ignora permissões de escrita")
    def test_validate_directory_rejects_readonly(self, tmp_path: Path) -> None:
        ro = tmp_path / "ro"
        ro.mkdir()
        ro.chmod(0o500)
        try:
            with pytest.raises(InvalidDestinationError):
                files.validate_directory(ro)
        finally:
            ro.chmod(0o700)

    def test_check_free_space(self, tmp_path: Path) -> None:
        files.check_free_space(tmp_path, 0)
        files.check_free_space(tmp_path, 1024)
        with pytest.raises(InsufficientSpaceError):
            files.check_free_space(tmp_path, 1 << 60)

    def test_delete_download_files_removes_file_and_control(self, tmp_path: Path) -> None:
        (tmp_path / "a.bin").write_bytes(b"1")
        (tmp_path / "a.bin.aria2").write_bytes(b"1")
        (tmp_path / "other.bin").write_bytes(b"1")
        removed = files.delete_download_files(tmp_path, "a.bin")
        assert {p.name for p in removed} == {"a.bin", "a.bin.aria2"}
        assert (tmp_path / "other.bin").exists()
        assert files.delete_download_files(tmp_path, "a.bin") == []

    def test_delete_download_files_blocks_traversal(self, tmp_path: Path) -> None:
        outside = tmp_path.parent / "keep.txt"
        outside.write_text("x")
        sub = tmp_path / "sub"
        sub.mkdir()
        with pytest.raises(InvalidDestinationError):
            files.delete_download_files(sub, "../../keep.txt")
        assert outside.exists()

    @pytest.mark.parametrize(
        ("name", "category"),
        [("a.MP4", "video"), ("a.flac", "music"), ("a.pdf", "document"), ("a.png", "image"),
         ("a.deb", "program"), ("a.tar", "archive"), ("a.xyz", "other"), ("semext", "other")],
    )
    def test_category(self, name: str, category: str) -> None:
        assert files.category_for(name) == category


class TestFormatting:
    def test_size(self) -> None:
        assert format_size(0) == "0 B"
        assert format_size(1023) == "1023 B"
        assert format_size(1536) == "1.50 KB"
        assert format_size(5 * 1024**3) == "5.00 GB"

    def test_speed_and_eta(self) -> None:
        assert format_speed(1024 * 1024) == "1.00 MB/s"
        assert format_eta(3725) == "01:02:05"
        assert format_eta(None) == "—"
        assert format_eta(100 * 3600) == "—"


class TestLogRedaction:
    @pytest.mark.parametrize(
        ("raw", "secret"),
        [
            ("params token:abc123 enviado", "abc123"),
            ("rpc-secret=supersecret", "supersecret"),
            ("Authorization: Bearer xyz", "xyz"),
            ("GET https://u:hunter2@host/f", "hunter2"),
            ("https://h/f?access_token=ttt&a=1", "ttt"),
            ("Cookie: sid=zzz", "zzz"),
        ],
    )
    def test_redact(self, raw: str, secret: str) -> None:
        assert secret not in redact(raw)

    def test_filter_applies_to_records(self) -> None:
        record = logging.LogRecord("n", logging.INFO, "f", 1, "pedido com token:%s", ("segredo",), None)
        RedactingFilter().filter(record)
        assert "segredo" not in record.getMessage()
