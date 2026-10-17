"""Montagem da aplicação: caminhos, base de dados, definições, tema, traduções, controlador e janela."""

from __future__ import annotations

import logging
import signal
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication

from nova_dm import APP_ID, APP_NAME, __version__
from nova_dm.config import AppPaths, Settings
from nova_dm.database.repository import Repository
from nova_dm.i18n import install_translators
from nova_dm.services.download_controller import DownloadController, EngineFactory, default_engine_factory
from nova_dm.ui import icons
from nova_dm.ui.main_window import MainWindow
from nova_dm.ui.styles import apply_theme
from nova_dm.utils.logging_setup import setup_logging

log = logging.getLogger(__name__)


class NovaDMApp:
    """Agrupa os objetos da aplicação. Permite arrancar com caminhos e motor alternativos (testes)."""

    def __init__(self, paths: AppPaths | None = None, engine_factory: EngineFactory = default_engine_factory,
                 argv: list[str] | None = None) -> None:
        self.paths = paths or AppPaths.default()
        self.paths.ensure()
        setup_logging(self.paths.log_dir)
        log.info("A iniciar %s %s", APP_NAME, __version__)

        existing = QApplication.instance()
        self.qt: QApplication = existing if isinstance(existing, QApplication) else QApplication(argv or sys.argv)
        self.qt.setApplicationName(APP_NAME)
        self.qt.setApplicationDisplayName(APP_NAME)
        self.qt.setApplicationVersion(__version__)
        self.qt.setDesktopFileName(APP_ID)
        self.qt.setWindowIcon(icons.logo_icon())

        self.repository = Repository(self.paths.database_file)
        self.settings = Settings.load(self.repository)
        self.settings.save(self.repository)

        install_translators(self.qt, self.settings.language)
        apply_theme(self.qt, self.settings.theme)

        self.controller = DownloadController(self.repository, self.paths, self.settings, engine_factory)
        self.window = MainWindow(self.settings, self.repository, self.controller)
        self.qt.aboutToQuit.connect(self.shutdown)

    def run(self) -> int:
        self.window.show()
        self.controller.start()
        # Permite Ctrl+C no terminal: o Qt só entrega sinais Unix com o ciclo de eventos «acordado».
        signal.signal(signal.SIGINT, lambda *_: self.window.close())
        signal.signal(signal.SIGTERM, lambda *_: self.window.close())
        wake = QTimer()
        wake.start(250)
        wake.timeout.connect(lambda: None)
        code = self.qt.exec()
        self.shutdown()
        return int(code)

    def shutdown(self) -> None:
        self.controller.shutdown()
        try:
            self.repository.close()
        except Exception:  # noqa: BLE001 - já fechada
            log.debug("Base de dados já estava fechada", exc_info=True)


def configure_high_dpi() -> None:
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)


