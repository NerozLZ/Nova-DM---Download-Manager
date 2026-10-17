#!/usr/bin/env python3
"""Extrai as frases marcadas com ``tr()`` e atualiza os ficheiros ``.ts`` (mantém as traduções existentes).

Utilização::

    python scripts/update_translations.py             # atualiza todos os .ts existentes
    python scripts/update_translations.py --new de    # cria um idioma novo (ex.: de, pt_PT)

As frases novas ficam «unfinished» (sem tradução) até serem traduzidas, por exemplo com o Qt Linguist
(``pyside6-linguist src/nova_dm/translations/nova_dm_de.ts``). Depois execute
``python scripts/compile_translations.py``.
"""

from __future__ import annotations

import argparse
import ast
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIR = ROOT / "src" / "nova_dm"
TRANSLATIONS_DIR = SOURCE_DIR / "translations"
CONTEXT = "NovaDM"
SOURCE_LANGUAGE = "en"


def extract_sources() -> list[str]:
    """Frases literais passadas a ``tr()``, pela ordem em que aparecem no código."""
    found: list[str] = []
    for path in sorted(SOURCE_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            func = node.func
            name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else None
            if name != "tr":
                continue
            first = node.args[0]
            if not (isinstance(first, ast.Constant) and isinstance(first.value, str)):
                raise SystemExit(f"{path}:{node.lineno}: tr() só aceita texto literal (para poder ser extraído)")
            if first.value not in found:
                found.append(first.value)
    return found


def read_existing(path: Path) -> dict[str, str]:
    """Traduções já concluídas num .ts."""
    if not path.exists():
        return {}
    result: dict[str, str] = {}
    for message in ET.parse(path).getroot().iterfind(f"./context[name='{CONTEXT}']/message"):
        source = message.findtext("source") or ""
        translation = message.find("translation")
        if translation is not None and translation.get("type") is None and translation.text:
            result[source] = translation.text
    return result


def write_ts(path: Path, code: str, sources: list[str], translations: dict[str, str]) -> int:
    """Escreve o .ts. Devolve quantas frases ficaram por traduzir."""
    pending = 0
    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        "<!DOCTYPE TS>",
        f'<TS version="2.1" language="{code}" sourcelanguage="{SOURCE_LANGUAGE}">',
        "<context>",
        f"    <name>{CONTEXT}</name>",
    ]
    for source in sources:
        text = translations.get(source)
        lines.append("    <message>")
        lines.append(f"        <source>{escape(source)}</source>")
        if text:
            lines.append(f"        <translation>{escape(text)}</translation>")
        else:
            pending += 1
            lines.append('        <translation type="unfinished"></translation>')
        lines.append("    </message>")
    lines += ["</context>", "</TS>", ""]
    path.write_text("\n".join(lines), encoding="utf-8")
    return pending


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--new", metavar="CODE", action="append", default=[], help="criar o idioma CODE")
    args = parser.parse_args()

    TRANSLATIONS_DIR.mkdir(parents=True, exist_ok=True)
    sources = extract_sources()
    targets = {p: p.stem.removeprefix("nova_dm_") for p in TRANSLATIONS_DIR.glob("nova_dm_*.ts")}
    for code in args.new:
        targets[TRANSLATIONS_DIR / f"nova_dm_{code}.ts"] = code

    if not targets:
        print("Não há ficheiros .ts. Use --new CODE para criar um idioma.", file=sys.stderr)
        return 1
    for path, code in sorted(targets.items(), key=lambda item: item[1]):
        pending = write_ts(path, code, sources, read_existing(path))
        print(f"{path.name}: {len(sources)} frases, {pending} por traduzir")
    return 0


if __name__ == "__main__":
    sys.exit(main())
