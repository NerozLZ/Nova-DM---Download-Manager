"""Diálogo «Adicionar download»: um ou vários URLs, nome, pasta e metadados."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from nova_dm.config import MAX_CONNECTIONS, MIN_CONNECTIONS, Settings
from nova_dm.errors import ProbeError
from nova_dm.i18n import tr
from nova_dm.services.metadata_service import UrlMetadata, probe_url
from nova_dm.utils.formatting import format_size
from nova_dm.utils.urls import extract_urls

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AddRequest:
    urls: list[str]
    directory: str
    filename: str
    connections: int
    size_hint: int
    start: bool


class _ProbeSignals(QObject):
    finished = Signal(str, object)  # url, UrlMetadata
    failed = Signal(str, str)  # url, mensagem


class _ProbeTask(QRunnable):
    def __init__(self, url: str) -> None:
        super().__init__()
        self.url = url
        self.signals = _ProbeSignals()

    def run(self) -> None:
        try:
            metadata = probe_url(self.url)
        except ProbeError as exc:
            self.signals.failed.emit(self.url, str(exc))
        except Exception:  # noqa: BLE001 - não pode escapar da thread do pool
            log.exception("Falha inesperada ao obter metadados")
            self.signals.failed.emit(self.url, tr("Unexpected error while contacting the server."))
        else:
            self.signals.finished.emit(self.url, metadata)


class AddDownloadDialog(QDialog):
    def __init__(self, settings: Settings, initial_text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Add download"))
        self.setMinimumWidth(560)
        self._settings = settings
        self._metadata: UrlMetadata | None = None
        self._probe_tasks: list[_ProbeTask] = []  # mantém as tarefas (e sinais) vivas até terminarem
        self._name_edited = False
        self._probe_timer = QTimer(self)
        self._probe_timer.setSingleShot(True)
        self._probe_timer.setInterval(600)
        self._probe_timer.timeout.connect(self._start_probe)

        self._urls = QPlainTextEdit()
        self._urls.setPlaceholderText(tr("Paste one or more http:// or https:// links (one per line)"))
        self._urls.setFixedHeight(96)
        self._urls.setPlainText(initial_text)
        self._urls.textChanged.connect(self._on_urls_changed)

        self._name = QLineEdit()
        self._name.textEdited.connect(self._on_name_edited)

        self._folder = QLineEdit(settings.download_dir)
        browse = QPushButton(tr("Browse…"))
        browse.clicked.connect(self._browse)
        folder_row = QHBoxLayout()
        folder_row.addWidget(self._folder, 1)
        folder_row.addWidget(browse)

        self._connections = QSpinBox()
        self._connections.setRange(MIN_CONNECTIONS, MAX_CONNECTIONS)
        self._connections.setValue(settings.connections_per_download)

        self._start_now = QCheckBox(tr("Start downloading immediately"))
        self._start_now.setChecked(True)

        self._info = QLabel(tr("Paste a link to see its details."))
        self._info.setObjectName("Muted")
        self._info.setWordWrap(True)

        self._message = QLabel()
        self._message.setWordWrap(True)
        self._message.setStyleSheet("color: #f0506e;")

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.addRow(tr("Links"), self._urls)
        form.addRow("", self._info)
        form.addRow(tr("File name"), self._name)
        form.addRow(tr("Save to"), folder_row)
        form.addRow(tr("Connections"), self._connections)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self._ok = QPushButton(tr("Add"))
        self._ok.setObjectName("Primary")
        self._ok.setDefault(True)
        self._ok.setEnabled(False)
        buttons.addButton(self._ok, QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.addLayout(form)
        layout.addWidget(self._start_now)
        layout.addWidget(self._message)
        layout.addWidget(buttons)
        self._on_urls_changed()

    # Estado ------------------------------------------------------------

    def valid_urls(self) -> list[str]:
        return extract_urls(self._urls.toPlainText())

    def _on_name_edited(self) -> None:
        self._name_edited = True

    def _on_urls_changed(self) -> None:
        urls = self.valid_urls()
        self._ok.setEnabled(bool(urls))
        self._metadata = None
        self._message.clear()
        single = len(urls) == 1
        self._name.setEnabled(single)
        if not urls:
            self._info.setText(tr("Paste a link to see its details."))
        elif single:
            self._info.setText(tr("Contacting the server…"))
            self._probe_timer.start()
        else:
            self._info.setText(tr("{count} links ready to add.").format(count=len(urls)))
            self._probe_timer.stop()
            self._name.clear()
            self._name.setPlaceholderText(tr("Each file keeps the name given by its link"))

    # Metadados ---------------------------------------------------------

    def _start_probe(self) -> None:
        urls = self.valid_urls()
        if len(urls) != 1:
            return
        task = _ProbeTask(urls[0])
        task.signals.finished.connect(self._on_probe_finished)
        task.signals.failed.connect(self._on_probe_failed)
        self._probe_tasks.append(task)
        QThreadPool.globalInstance().start(task)

    def _is_current(self, url: str) -> bool:
        urls = self.valid_urls()
        return len(urls) == 1 and urls[0] == url

    def _on_probe_finished(self, url: str, metadata: UrlMetadata) -> None:
        if not self._is_current(url):
            return
        self._metadata = metadata
        size = format_size(metadata.size) if metadata.size else tr("unknown size")
        resume = tr("supports resume") if metadata.accepts_ranges else tr("no resume support")
        kind = f" · {metadata.content_type}" if metadata.content_type else ""
        self._info.setText(f"{size} · {resume}{kind}")
        if not self._name_edited:
            self._name.setText(metadata.filename)

    def _on_probe_failed(self, url: str, message: str) -> None:
        if not self._is_current(url):
            return
        self._info.setText(tr("Could not read the link details: {error}").format(error=message))

    # Ações -------------------------------------------------------------

    def _browse(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, tr("Choose folder"), self._folder.text())
        if chosen:
            self._folder.setText(chosen)

    def _accept(self) -> None:
        urls = self.valid_urls()
        if not urls:
            self._message.setText(tr("Enter at least one valid http:// or https:// link."))
            return
        if not self._folder.text().strip().startswith("/"):
            self._message.setText(tr("The destination folder must be an absolute path."))
            return
        self.accept()

    def request(self) -> AddRequest:
        urls = self.valid_urls()
        size = self._metadata.size if self._metadata and self._metadata.size else 0
        return AddRequest(
            urls=urls,
            directory=self._folder.text().strip(),
            filename=self._name.text().strip() if len(urls) == 1 else "",
            connections=self._connections.value(),
            size_hint=size if len(urls) == 1 else 0,
            start=self._start_now.isChecked(),
        )
