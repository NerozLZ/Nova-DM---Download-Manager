"""Diálogo com os detalhes de uma transferência."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from nova_dm.core.models import DownloadRecord
from nova_dm.i18n import tr
from nova_dm.ui.presentation import category_label, status_label
from nova_dm.utils.formatting import format_size, format_speed


def _local_time(iso: str | None) -> str:
    if not iso:
        return "—"
    try:
        return datetime.fromisoformat(iso).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return iso


class DetailsDialog(QDialog):
    def __init__(self, record: DownloadRecord, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Download details"))
        self.setMinimumWidth(560)
        self._record = record

        def value(text: str) -> QLabel:
            label = QLabel(text)
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            return label

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        total = format_size(record.total_bytes) if record.total_bytes else tr("Unknown size")
        rows = [
            (tr("File name"), record.filename),
            (tr("URL"), record.url),
            (tr("Save to"), record.directory),
            (tr("Status"), status_label(record.status)),
            (tr("Category"), category_label(record.category)),
            (tr("Size"), total),
            (tr("Downloaded"), f"{format_size(record.completed_bytes)} ({int(record.progress * 100)}%)"),
            (tr("Speed"), format_speed(record.download_speed) if record.download_speed else "—"),
            (tr("Connections"), str(record.connections or "—")),
            (tr("Added"), _local_time(record.created_at)),
            (tr("Finished"), _local_time(record.completed_at)),
        ]
        if record.error_message:
            rows.append((tr("Error"), record.error_message))
        for label, text in rows:
            form.addRow(f"{label}:", value(text))

        copy = QPushButton(tr("Copy URL"))
        copy.clicked.connect(lambda: QGuiApplication.clipboard().setText(self._record.url))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.addButton(copy, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)
