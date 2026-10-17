"""Licença do Nova DM e componentes de terceiros (textos incluídos no pacote)."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QPlainTextEdit, QTabWidget, QVBoxLayout, QWidget

from nova_dm import APP_NAME
from nova_dm.i18n import tr

log = logging.getLogger(__name__)

LEGAL_DIR = Path(__file__).resolve().parents[2] / "legal"


def read_legal(name: str) -> str:
    try:
        return (LEGAL_DIR / name).read_text(encoding="utf-8")
    except OSError:
        log.warning("Texto legal em falta: %s", name)
        return tr("The license text could not be found in this installation.")


class LicenseDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"{tr('License')} — {APP_NAME}")
        self.resize(720, 560)
        tabs = QTabWidget()
        for title, filename in ((tr("License"), "LICENSE.txt"), (tr("Third-party components"), "THIRD_PARTY.md")):
            view = QPlainTextEdit(read_legal(filename))
            view.setReadOnly(True)
            tabs.addTab(view, title)
        buttons = QDialogButtonBox()
        close = buttons.addButton(tr("Close"), QDialogButtonBox.ButtonRole.RejectRole)
        close.clicked.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(tabs, 1)
        layout.addWidget(buttons)
