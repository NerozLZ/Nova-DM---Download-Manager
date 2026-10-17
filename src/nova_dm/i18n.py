"""Traduções (sistema de ficheiros .ts/.qm do Qt).

As frases de origem estão em inglês e passam sempre por `tr()`. Para acrescentar um idioma:
`python scripts/update_translations.py <código>` e `python scripts/compile_translations.py`.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QLibraryInfo, QLocale, QTranslator

log = logging.getLogger(__name__)

CONTEXT = "NovaDM"
TRANSLATIONS_DIR = Path(__file__).parent / "translations"
SOURCE_LANGUAGE = "en"

_active: list[QTranslator] = []


def tr(text: str, disambiguation: str | None = None) -> str:
    return QCoreApplication.translate(CONTEXT, text, disambiguation)


def available_languages() -> list[str]:
    """Códigos de idioma disponíveis (inglês e todos os .qm presentes)."""
    codes = {p.stem.removeprefix("nova_dm_") for p in TRANSLATIONS_DIR.glob("nova_dm_*.qm")}
    return [SOURCE_LANGUAGE, *sorted(codes - {SOURCE_LANGUAGE})]


_NAME_OVERRIDES = {"en": "English", "pt_PT": "Português (Portugal)", "es": "Español"}


def language_name(code: str) -> str:
    """Nome do idioma na sua própria língua (ex.: «Português (Portugal)»)."""
    if code in _NAME_OVERRIDES:
        return _NAME_OVERRIDES[code]
    locale = QLocale(code)
    name = locale.nativeLanguageName()
    territory = locale.nativeTerritoryName()
    text = name[:1].upper() + name[1:] if name else code
    return f"{text} ({territory})" if territory and code.count("_") else text


def resolve_language(preference: str) -> str:
    """Converte «system» (ou um código) num idioma disponível."""
    languages = available_languages()
    if preference != "system":
        return preference if preference in languages else SOURCE_LANGUAGE
    for system_name in QLocale.system().uiLanguages():
        normalized = system_name.replace("-", "_")
        if normalized in languages:
            return normalized
        base = normalized.split("_")[0]
        for code in languages:
            if code.split("_")[0] == base:
                return code
    return SOURCE_LANGUAGE


def install_translators(app: QCoreApplication, preference: str) -> str:
    """Instala as traduções do Nova DM e as do Qt (botões de diálogos). Devolve o idioma usado."""
    for translator in _active:
        app.removeTranslator(translator)
    _active.clear()
    code = resolve_language(preference)
    if code == SOURCE_LANGUAGE:
        return code

    own = QTranslator(app)
    if own.load(str(TRANSLATIONS_DIR / f"nova_dm_{code}.qm")):
        app.installTranslator(own)
        _active.append(own)
    else:
        log.warning("Não foi possível carregar a tradução %s", code)

    qt_translator = QTranslator(app)
    qt_dir = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    for candidate in (code, code.split("_")[0]):
        if qt_translator.load(f"qtbase_{candidate}", qt_dir):
            app.installTranslator(qt_translator)
            _active.append(qt_translator)
            break
    return code
