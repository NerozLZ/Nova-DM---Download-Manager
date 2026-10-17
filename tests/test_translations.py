"""Verifica que todas as traduções estão completas, coerentes e carregáveis."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

import pytest
from PySide6.QtCore import QCoreApplication, QTranslator

from nova_dm.i18n import CONTEXT, TRANSLATIONS_DIR, available_languages, language_name, resolve_language, tr

TS_FILES = sorted(TRANSLATIONS_DIR.glob("nova_dm_*.ts"))
PLACEHOLDER = re.compile(r"\{\w+\}")


def _messages(path):
    root = ET.parse(path).getroot()
    for message in root.iter("message"):
        yield message.findtext("source") or "", message.find("translation")


def test_there_are_translations() -> None:
    assert len(TS_FILES) >= 25


@pytest.mark.parametrize("ts", TS_FILES, ids=lambda p: p.stem)
def test_translation_is_complete_and_consistent(ts) -> None:
    count = 0
    for source, translation in _messages(ts):
        count += 1
        text = translation.text or ""
        assert translation.get("type") is None, f"{ts.name}: por terminar: {source!r}"
        assert text.strip(), f"{ts.name}: vazia: {source!r}"
        assert sorted(PLACEHOLDER.findall(source)) == sorted(PLACEHOLDER.findall(text)), f"{ts.name}: {source!r}"
        assert source.count("\n") == text.count("\n"), f"{ts.name}: quebras de linha: {source!r}"
    assert count > 100


@pytest.mark.parametrize("ts", TS_FILES, ids=lambda p: p.stem)
def test_compiled_file_exists_and_loads(qapp, ts) -> None:
    qm = ts.with_suffix(".qm")
    assert qm.exists(), f"falta {qm.name}"
    translator = QTranslator()
    assert translator.load(str(qm))
    assert translator.translate(CONTEXT, "Settings")


def test_all_languages_are_offered() -> None:
    codes = available_languages()
    assert codes[0] == "en"
    assert {ts.stem.removeprefix("nova_dm_") for ts in TS_FILES} <= set(codes)
    assert all(language_name(code) for code in codes)


def test_resolve_language_falls_back_to_english() -> None:
    assert resolve_language("xx_YY") == "en"
    assert resolve_language("pt_PT") == "pt_PT"


def test_tr_uses_installed_translator(qapp) -> None:
    translator = QTranslator()
    assert translator.load(str(TRANSLATIONS_DIR / "nova_dm_pt_PT.qm"))
    QCoreApplication.installTranslator(translator)
    try:
        assert tr("Settings") != "Settings"
    finally:
        QCoreApplication.removeTranslator(translator)


def test_packaged_legal_texts_match_the_repository_root() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    legal = root / "src" / "nova_dm" / "legal"
    assert (legal / "LICENSE.txt").read_text(encoding="utf-8") == (root / "LICENSE").read_text(encoding="utf-8")
    assert (legal / "THIRD_PARTY.md").read_text(encoding="utf-8") == (root / "THIRD_PARTY.md").read_text(encoding="utf-8")
