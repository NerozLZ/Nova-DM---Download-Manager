"""Página de definições."""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from nova_dm import APP_NAME, __version__
from nova_dm.config import (
    BROWSER_PORT_MAX,
    BROWSER_PORT_MIN,
    MAX_CONCURRENT_LIMIT,
    MAX_CONNECTIONS,
    MIN_CONNECTIONS,
    Settings,
)
from nova_dm.services.browser_bridge import generate_token
from nova_dm.i18n import available_languages, language_name, tr
from nova_dm.ui.dialogs.license_dialog import LicenseDialog


class SettingsPage(QWidget):
    settings_saved = Signal(object)  # Settings

    def __init__(self, settings: Settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = settings

        self._folder = QLineEdit()
        browse = QPushButton(tr("Browse…"))
        browse.clicked.connect(self._browse)
        folder_row = QHBoxLayout()
        folder_row.addWidget(self._folder, 1)
        folder_row.addWidget(browse)

        self._theme = QComboBox()
        self._theme.addItem(tr("Dark"), "dark")
        self._theme.addItem(tr("Light"), "light")

        self._language = QComboBox()
        self._language.addItem(tr("System default"), "system")
        for code in available_languages():
            self._language.addItem(language_name(code), code)

        self._concurrent = QSpinBox()
        self._concurrent.setRange(1, MAX_CONCURRENT_LIMIT)
        self._connections = QSpinBox()
        self._connections.setRange(MIN_CONNECTIONS, MAX_CONNECTIONS)
        self._limit = QSpinBox()
        self._limit.setRange(0, 10_000_000)
        self._limit.setSuffix(" KiB/s")
        self._limit.setSpecialValueText(tr("Unlimited"))
        self._limit.setSingleStep(100)

        self._confirm_delete = QCheckBox(tr("Ask for confirmation before deleting files"))
        self._auto_resume = QCheckBox(tr("Resume unfinished downloads when the app starts"))
        # Campo do executável do aria2: já não é mostrado, mas o valor guardado é preservado ao gravar.
        self._aria2_path = QLineEdit(self)
        self._aria2_path.hide()

        self._browser_enabled = QCheckBox(tr("Accept links sent by the browser extension"))
        self._browser_confirm = QCheckBox(tr("Ask before adding links sent by the browser"))
        self._browser_port = QSpinBox()
        self._browser_port.setRange(BROWSER_PORT_MIN, BROWSER_PORT_MAX)
        self._browser_token = QLineEdit()
        self._browser_token.setReadOnly(True)
        self._browser_token.setPlaceholderText(tr("(generated when enabled)"))
        copy_token = QPushButton(tr("Copy"))
        copy_token.clicked.connect(self._copy_token)
        new_token = QPushButton(tr("Generate new token"))
        new_token.clicked.connect(self._new_token)
        token_row = QHBoxLayout()
        token_row.addWidget(self._browser_token, 1)
        token_row.addWidget(copy_token)
        token_row.addWidget(new_token)

        title = QLabel(tr("Settings"))
        title.setObjectName("Title")

        general = self._section(tr("General"), [
            (tr("Download folder"), folder_row),
            (tr("Theme"), self._theme),
            (tr("Language"), self._language),
        ])
        transfers = self._section(tr("Transfers"), [
            (tr("Simultaneous downloads"), self._concurrent),
            (tr("Connections per download"), self._connections),
            (tr("Global speed limit"), self._limit),
        ])
        behaviour = self._section(tr("Behaviour"), [("", self._confirm_delete), ("", self._auto_resume)])
        browser_note = QLabel(tr("Only programs on this computer can connect. Install the Nova DM extension in Firefox "
                                 "and click Connect in its options; the token is only needed for a manual setup."))
        browser_note.setObjectName("Muted")
        browser_note.setWordWrap(True)
        browser = self._section(tr("Browser integration"), [
            ("", self._browser_enabled),
            ("", self._browser_confirm),
            (tr("Port"), self._browser_port),
            (tr("Access token"), token_row),
        ])
        browser_layout = browser.layout()
        assert browser_layout is not None
        browser_layout.addSpacing(6)
        browser_layout.addWidget(browser_note)

        license_text = QLabel(tr("Freeware: free to use, personal or commercial. It may not be sold or bundled in paid products."))
        license_text.setWordWrap(True)
        view_license = QPushButton(tr("View license and third-party components"))
        view_license.clicked.connect(lambda: LicenseDialog(self).exec())
        license_row = QHBoxLayout()
        license_row.addWidget(view_license)
        license_row.addStretch(1)
        about = self._section(tr("About"), [
            (tr("Version"), QLabel(f"{APP_NAME} {__version__}")),
            ("", QLabel("Copyright 2026 by NerozLZ")),
        ])
        about_layout = about.layout()
        assert about_layout is not None
        about_layout.addSpacing(6)
        about_layout.addWidget(license_text)  # fora do QFormLayout: o texto longo quebra linha sem ser cortado
        about_layout.addSpacing(6)
        about_layout.addLayout(license_row)

        self._status = QLabel()
        self._status.setObjectName("Muted")
        save = QPushButton(tr("Save"))
        save.setObjectName("Primary")
        save.clicked.connect(self._save)
        reset = QPushButton(tr("Discard changes"))
        reset.clicked.connect(lambda: self.load(self._settings))
        actions = QHBoxLayout()
        actions.addWidget(save)
        actions.addWidget(reset)
        actions.addWidget(self._status, 1)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(28, 24, 28, 24)
        content_layout.setSpacing(18)
        for widget in (title, general, transfers, behaviour, browser, about):
            content_layout.addWidget(widget)
        content_layout.addLayout(actions)
        content_layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content.setObjectName("SettingsContent")  # fundo transparente definido em styles.py (com seletor)
        scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
        self.load(settings)

    @staticmethod
    def _section(title: str, rows: list[tuple[str, QWidget | QHBoxLayout]]) -> QFrame:
        frame = QFrame()
        frame.setObjectName("Panel")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(20, 16, 20, 18)
        heading = QLabel(title)
        heading.setObjectName("SectionTitle")
        layout.addWidget(heading)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form.setHorizontalSpacing(24)
        form.setVerticalSpacing(12)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        for label, field in rows:
            if isinstance(field, QHBoxLayout):
                form.addRow(label, field)
            else:
                form.addRow(label, field)
        layout.addLayout(form)
        return frame

    def load(self, settings: Settings) -> None:
        self._settings = settings
        self._folder.setText(settings.download_dir)
        self._theme.setCurrentIndex(max(0, self._theme.findData(settings.theme)))
        self._language.setCurrentIndex(max(0, self._language.findData(settings.language)))
        self._concurrent.setValue(settings.max_concurrent)
        self._connections.setValue(settings.connections_per_download)
        self._limit.setValue(settings.global_speed_limit_kib)
        self._confirm_delete.setChecked(settings.confirm_delete)
        self._auto_resume.setChecked(settings.auto_resume)
        self._aria2_path.setText(settings.aria2_path)
        self._browser_enabled.setChecked(settings.browser_integration)
        self._browser_port.setValue(settings.browser_port)
        self._browser_confirm.setChecked(settings.browser_confirm)
        self._browser_token.setText(settings.browser_token)
        self._status.clear()

    def _new_token(self) -> None:
        self._browser_token.setText(generate_token())
        self._status.setText("")

    def _copy_token(self) -> None:
        if not self._browser_token.text():
            self._browser_token.setText(generate_token())
        QGuiApplication.clipboard().setText(self._browser_token.text())

    def _browse(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, tr("Choose folder"), self._folder.text())
        if chosen:
            self._folder.setText(chosen)

    def _save(self) -> None:
        updated = replace(
            self._settings,
            download_dir=self._folder.text(),
            theme=self._theme.currentData(),
            language=self._language.currentData(),
            max_concurrent=self._concurrent.value(),
            connections_per_download=self._connections.value(),
            global_speed_limit_kib=self._limit.value(),
            confirm_delete=self._confirm_delete.isChecked(),
            auto_resume=self._auto_resume.isChecked(),
            aria2_path=self._aria2_path.text(),
            browser_integration=self._browser_enabled.isChecked(),
            browser_port=self._browser_port.value(),
            browser_confirm=self._browser_confirm.isChecked(),
            browser_token=self._browser_token.text() or (generate_token() if self._browser_enabled.isChecked() else ""),
        ).normalized()
        self._browser_token.setText(updated.browser_token)
        self._settings = updated
        self.settings_saved.emit(updated)
        self._status.setText(tr("Settings saved."))
