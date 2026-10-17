#!/usr/bin/env python3
"""Compila os ficheiros ``.ts`` em ``.qm`` (formato binário que o Qt carrega em execução).

Utilização: ``python scripts/compile_translations.py``

Usa o ``lrelease`` que acompanha o PySide6 (``pyside6-lrelease``) ou o do sistema.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

TRANSLATIONS_DIR = Path(__file__).resolve().parent.parent / "src" / "nova_dm" / "translations"


def find_lrelease() -> str:
    candidates = [
        Path(sys.executable).parent / "pyside6-lrelease",
        shutil.which("pyside6-lrelease"),
        shutil.which("lrelease"),
        shutil.which("lrelease-qt6"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return str(candidate)
    raise SystemExit("lrelease não encontrado. Instale o PySide6 (pip install PySide6) ou as ferramentas Qt.")


def main() -> int:
    lrelease = find_lrelease()
    sources = sorted(TRANSLATIONS_DIR.glob("nova_dm_*.ts"))
    if not sources:
        print("Não há ficheiros .ts para compilar.", file=sys.stderr)
        return 1
    failed = 0
    for ts_file in sources:
        qm_file = ts_file.with_suffix(".qm")
        result = subprocess.run([lrelease, "-silent", str(ts_file), "-qm", str(qm_file)],
                                capture_output=True, text=True, check=False)
        if result.returncode != 0:
            failed += 1
            print(f"ERRO a compilar {ts_file.name}: {result.stderr.strip()}", file=sys.stderr)
    print(f"{len(sources) - failed}/{len(sources)} ficheiros compilados em {TRANSLATIONS_DIR}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
