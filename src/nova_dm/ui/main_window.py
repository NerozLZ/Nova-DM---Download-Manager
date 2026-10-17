"""Janela principal."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QPoint, QTimer, QUrl, Qt
from PySide6.QtGui import (
    QAction,
    QCloseEvent,
    QDesktopServices,
    QDragEnterEvent,
    QDropEvent,
    QGuiApplication,
    QKeySequence,
    QShortcut,
)
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from nova_dm import APP_NAME
from nova_dm.config import Settings
from nova_dm.core.models import DownloadRecord, DownloadStatus, RequestContext
from nova_dm.database.repository import Repository
from nova_dm.i18n import tr
from nova_dm.services.browser_bridge import BrowserBridge
from nova_dm.services.download_controller import DownloadController
from nova_dm.services.download_service import AddResult
from nova_dm.ui import icons
from nova_dm.ui.dialogs.add_download_dialog import AddDownloadDialog
from nova_dm.ui.dialogs.details_dialog import DetailsDialog
from nova_dm.ui.download_model import DownloadModel
from nova_dm.ui.pages.downloads_page import DownloadsPage
from nova_dm.ui.pages.settings_page import SettingsPage
from nova_dm.ui.widgets.download_list import dropped_links
from nova_dm.ui.styles import apply_theme, current_palette
from nova_dm.ui.widgets.sidebar import Sidebar
from nova_dm.utils.files import CATEGORIES
from nova_dm.utils.formatting import format_speed
from nova_dm.utils.urls import extract_urls

log = logging.getLogger(__name__)

_PENDING = (DownloadStatus.ACTIVE, DownloadStatus.QUEUED)


class MainWindow(QMainWindow):
    def __init__(self, settings: Settings, repository: Repository, controller: DownloadController) -> None:
        super().__init__()
        self._settings = settings
        self._repo = repository
        self._controller = controller
        self._records: dict[int, DownloadRecord] = {}
        self._closing_confirmed = False
        self._shutting_down = False
        self._add_dialog_open = False
        self._browser_queue: list[tuple[list[str], dict[str, str]]] = []

        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(icons.logo_icon())
        self.setAcceptDrops(True)
        self.resize(1320, 780)
        self.setMinimumSize(1000, 560)

        self.model = DownloadModel(self)
        self.sidebar = Sidebar()
        self.page = DownloadsPage(self.model)
        self.settings_page = SettingsPage(settings)

        self._bridge = BrowserBridge(self)
        self._bridge.links_received.connect(self._on_browser_links)
        self._bridge.pair_requested.connect(self._on_pair_requested)
        self._bridge.failed.connect(
            lambda error: self.statusBar().showMessage(
                tr("Browser integration could not start: {error}").format(error=error), 10000)
        )

        self._build_layout()
        self._build_actions()
        self._connect_signals()
        self._refresh_theme_icons()
        self._apply_browser_integration()

    # Construção ---------------------------------------------------------

    def _build_layout(self) -> None:
        self.search = QLineEdit()
        self.search.setObjectName("Search")
        self.search.setPlaceholderText(tr("Search downloads…"))
        self.search.setClearButtonEnabled(True)
        self._search_action = self.search.addAction(icons.icon("search", "#8d93a8", 18), QLineEdit.ActionPosition.LeadingPosition)

        self.add_button = QPushButton()
        self.add_button.setObjectName("Primary")
        self.add_button.setFixedSize(46, 46)
        self.add_button.setToolTip(tr("Add download") + "  (Ctrl+N)")
        self.add_button.setAccessibleName(tr("Add download"))

        self.pause_all_button = QPushButton()
        self.pause_all_button.setObjectName("Icon")
        self.pause_all_button.setToolTip(tr("Pause all"))
        self.pause_all_button.setAccessibleName(tr("Pause all"))
        self.resume_all_button = QPushButton()
        self.resume_all_button.setObjectName("Icon")
        self.resume_all_button.setToolTip(tr("Resume all"))
        self.resume_all_button.setAccessibleName(tr("Resume all"))

        self.delete_button = QPushButton()
        self.delete_button.setObjectName("Icon")
        self.delete_button.setToolTip(tr("Remove selected") + "  (Del)")
        self.delete_button.setAccessibleName(tr("Remove selected"))
        self.delete_button.setEnabled(False)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)
        toolbar.addWidget(self.search, 1)
        toolbar.addWidget(self.delete_button)
        toolbar.addWidget(self.pause_all_button)
        toolbar.addWidget(self.resume_all_button)
        toolbar.addWidget(self.add_button)

        self.banner = QLabel()
        self.banner.setWordWrap(True)
        self.banner.setVisible(False)
        self.banner.setStyleSheet(
            "background: rgba(240,80,110,0.14); color: #f0506e; border: 1px solid #f0506e; "
            "border-radius: 10px; padding: 10px 14px;"
        )

        self.stack = QStackedWidget()
        self.stack.addWidget(self.page)
        self.stack.addWidget(self.settings_page)

        self.toolbar_widget = QWidget()
        self.toolbar_widget.setLayout(toolbar)

        right = QVBoxLayout()
        right.setContentsMargins(18, 18, 18, 8)
        right.setSpacing(12)
        right.addWidget(self.toolbar_widget)
        right.addWidget(self.banner)
        right.addWidget(self.stack, 1)

        root = QWidget()
        root.setObjectName("Root")
        row = QHBoxLayout(root)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addWidget(self.sidebar)
        row.addLayout(right, 1)
        self.setCentralWidget(root)

        self._status_engine = QLabel(tr("Starting download engine…"))
        self._status_speed = QLabel()
        self.statusBar().addWidget(self._status_engine, 1)
        self.statusBar().addPermanentWidget(self._status_speed)
        self.statusBar().setSizeGripEnabled(False)

    def _build_actions(self) -> None:
        def shortcut(keys: str | QKeySequence.StandardKey, handler) -> None:  # noqa: ANN001
            QShortcut(QKeySequence(keys), self, activated=handler)

        shortcut("Ctrl+N", self.add_download)
        shortcut("Ctrl+V", self.paste_from_clipboard)
        shortcut("Ctrl+F", self._focus_search)
        shortcut("Ctrl+,", lambda: self.sidebar.select("settings"))
        shortcut("Ctrl+Q", self.close)
        shortcut("Space", self._toggle_selected)
        shortcut("Return", self._open_selected)
        shortcut("Delete", lambda: self._remove(self.page.selected_ids()))
        shortcut("Shift+Delete", lambda: self._delete_files(self.page.selected_ids()))
        shortcut("Ctrl+A", self._select_all)
        shortcut("Alt+Up", lambda: self._move(self.page.selected_ids(), "up"))
        shortcut("Alt+Down", lambda: self._move(self.page.selected_ids(), "down"))

    def _connect_signals(self) -> None:
        self.sidebar.selected.connect(self._on_nav)
        self.search.textChanged.connect(self.page.proxy.set_search_text)
        self.add_button.clicked.connect(lambda: self.add_download())
        self.pause_all_button.clicked.connect(self._pause_all)
        self.resume_all_button.clicked.connect(self._resume_all)
        self.page.primary_clicked.connect(self._on_primary)
        self.page.menu_requested.connect(self._on_row_menu)
        self.page.context_menu_requested.connect(lambda pos: self._show_menu(self.page.selected_ids(), pos))
        self.page.open_requested.connect(self._on_double_click)
        self.page.rows_moved.connect(self._on_rows_moved)
        self.page.links_dropped.connect(self._on_links_dropped)
        self.page.selection_changed.connect(self._on_selection_changed)
        self.delete_button.clicked.connect(lambda: self._remove(self.page.selected_ids()))
        self.settings_page.settings_saved.connect(self._on_settings_saved)
        c = self._controller
        c.records_changed.connect(self._on_records)
        c.error.connect(self.show_error)
        c.engine_ready.connect(self._on_engine_ready)
        c.engine_failed.connect(self._on_engine_failed)
        c.add_finished.connect(self._on_add_finished)

    def _refresh_theme_icons(self) -> None:
        p = current_palette()
        self.add_button.setIcon(icons.icon("plus", "#ffffff", 22))
        self.pause_all_button.setIcon(icons.icon("pause", p.text, 20))
        self.resume_all_button.setIcon(icons.icon("play", p.text, 20))
        self.delete_button.setIcon(icons.icon("trash", p.text, 20))
        self._search_action.setIcon(icons.icon("search", p.text_muted, 18))
        self.sidebar.refresh_theme()

    # Interface do utilizador (substituíveis em testes) -------------------

    def show_error(self, message: str) -> None:
        QMessageBox.warning(self, APP_NAME, message)

    def confirm(self, title: str, text: str, *, destructive: bool = False) -> bool:
        box = QMessageBox(QMessageBox.Icon.Warning if destructive else QMessageBox.Icon.Question, title, text,
                          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, self)
        box.setDefaultButton(QMessageBox.StandardButton.No)
        return box.exec() == QMessageBox.StandardButton.Yes

    # Dados --------------------------------------------------------------

    def _on_records(self, records: list[DownloadRecord]) -> None:
        self._records = {r.id: r for r in records if r.id is not None}
        self.model.set_records(records)
        counts = {
            "all": len(records),
            "active": sum(r.status is DownloadStatus.ACTIVE for r in records),
            "queued": sum(r.status is DownloadStatus.QUEUED for r in records),
            "completed": sum(r.status is DownloadStatus.COMPLETED for r in records),
            "stopped": sum(r.status in (DownloadStatus.PAUSED, DownloadStatus.CANCELLED) for r in records),
            "failed": sum(r.status is DownloadStatus.FAILED for r in records),
        }
        for category in CATEGORIES:
            counts[f"cat:{category}"] = sum(r.category == category for r in records)
        self.sidebar.set_counts(counts)
        speed = sum(r.download_speed for r in records if r.status is DownloadStatus.ACTIVE)
        self._status_speed.setText(
            tr("{count} in progress").format(count=counts["active"]) + "  ·  " + format_speed(speed)
        )

    def _on_engine_ready(self) -> None:
        self._status_engine.clear()
        self.banner.setVisible(False)

    def _on_engine_failed(self, message: str) -> None:
        self._status_engine.setText(tr("Download engine unavailable"))
        self.banner.setText(message)
        self.banner.setVisible(True)

    def _on_add_finished(self, result: AddResult) -> None:
        if result.errors:
            lines = [f"{url or ''}: {msg}" if url else msg for url, msg in result.errors[:8]]
            if len(result.errors) > 8:
                lines.append(tr("…and {count} more.").format(count=len(result.errors) - 8))
            self.show_error(tr("Some links could not be added:") + "\n\n" + "\n".join(lines))
        if result.added:
            self.statusBar().showMessage(tr("{count} download(s) added").format(count=len(result.added)), 4000)
            if self.sidebar.current_key() in ("settings",):
                self.sidebar.select("all")

    # Navegação ----------------------------------------------------------

    def _on_nav(self, key: str) -> None:
        is_settings = key == "settings"
        self.stack.setCurrentWidget(self.settings_page if is_settings else self.page)
        self.toolbar_widget.setVisible(not is_settings)
        if not is_settings:
            self.page.proxy.set_filter_key(key)

    def _focus_search(self) -> None:
        if self.stack.currentWidget() is self.page:
            self.search.setFocus()
            self.search.selectAll()

    # Adicionar -----------------------------------------------------------

    def add_download(self, initial_text: str = "", context: RequestContext | None = None) -> None:
        dialog = AddDownloadDialog(self._settings, initial_text, self)
        self._add_dialog_open = True
        try:
            accepted = dialog.exec() == AddDownloadDialog.DialogCode.Accepted
        finally:
            self._add_dialog_open = False
            if self._browser_queue:
                QTimer.singleShot(0, self._drain_browser_queue)
        if not accepted:
            return
        req = dialog.request()
        self._controller.add(req.urls, req.directory, filename=req.filename, connections=req.connections,
                             size_hint=req.size_hint, start=req.start, context=context)

    def paste_from_clipboard(self) -> None:
        if isinstance(QApplication.focusWidget(), QLineEdit):
            focused = QApplication.focusWidget()
            if isinstance(focused, QLineEdit):
                focused.paste()
                return
        text = QGuiApplication.clipboard().text()
        if extract_urls(text):
            self.add_download(text)
        else:
            self.statusBar().showMessage(tr("The clipboard has no http:// or https:// links."), 4000)

    # Ações sobre transferências -----------------------------------------

    def _records_for(self, ids: list[int]) -> list[DownloadRecord]:
        return [self._records[i] for i in ids if i in self._records]

    def _on_primary(self, download_id: int, action: str) -> None:
        if action == "pause":
            self._controller.pause([download_id])
        elif action == "resume":
            self._controller.resume([download_id])
        elif action == "retry":
            self._controller.retry([download_id])
        elif action == "open":
            self._open_file(download_id)

    def _on_double_click(self, download_id: int) -> None:
        record = self._records.get(download_id)
        if record is None:
            return
        if record.status is DownloadStatus.COMPLETED:
            self._open_file(download_id)
        else:
            self._show_details(download_id)

    def _toggle_selected(self) -> None:
        records = self._records_for(self.page.selected_ids())
        if not records or not self.page.view.hasFocus():
            return
        if any(r.status in _PENDING for r in records):
            self._controller.pause([r.id for r in records if r.status in _PENDING and r.id is not None])
        else:
            self._controller.resume([r.id for r in records if r.status is DownloadStatus.PAUSED and r.id is not None])

    def _open_selected(self) -> None:
        ids = self.page.selected_ids()
        if len(ids) == 1 and self.page.view.hasFocus():
            self._on_double_click(ids[0])

    def _pause_all(self) -> None:
        self._controller.pause([i for i, r in self._records.items() if r.status in _PENDING])

    def _resume_all(self) -> None:
        self._controller.resume([i for i, r in self._records.items() if r.status is DownloadStatus.PAUSED])

    def _on_row_menu(self, download_id: int, pos: QPoint) -> None:
        selected = self.page.selected_ids()
        self._show_menu(selected if download_id in selected else [download_id], pos)

    def _show_menu(self, ids: list[int], pos: QPoint) -> None:
        records = self._records_for(ids)
        if not records:
            return
        menu = QMenu(self)
        p = current_palette()
        single = len(records) == 1

        def add(text: str, icon_name: str, handler) -> None:  # noqa: ANN001
            action = QAction(icons.icon(icon_name, p.text, 18), text, menu)
            action.triggered.connect(lambda _checked=False: handler())
            menu.addAction(action)

        statuses = {r.status for r in records}
        ids_of = lambda *wanted: [r.id for r in records if r.status in wanted and r.id is not None]  # noqa: E731
        if ids_of(*_PENDING):
            add(tr("Pause"), "pause", lambda: self._controller.pause(ids_of(*_PENDING)))
        if ids_of(DownloadStatus.PAUSED):
            add(tr("Resume"), "play", lambda: self._controller.resume(ids_of(DownloadStatus.PAUSED)))
        if ids_of(DownloadStatus.FAILED, DownloadStatus.CANCELLED):
            add(tr("Retry"), "retry", lambda: self._controller.retry(ids_of(DownloadStatus.FAILED, DownloadStatus.CANCELLED)))
        if any(s.is_pending for s in statuses):
            add(tr("Cancel download"), "x-circle", lambda: self._cancel([r.id for r in records if r.status.is_pending and r.id]))
        menu.addSeparator()
        if single:
            record = records[0]
            if record.status is DownloadStatus.COMPLETED:
                add(tr("Open file"), "file", lambda: self._open_file(record.id))
            add(tr("Open folder"), "folder", lambda: self._open_folder(record.id))
        add(tr("Copy URL"), "copy", lambda: QGuiApplication.clipboard().setText("\n".join(r.url for r in records)))
        if single:
            add(tr("Details"), "info", lambda: self._show_details(records[0].id))
        menu.addSeparator()
        order_ids = [r.id for r in records if r.id is not None]
        order_menu = menu.addMenu(icons.icon("queue", p.text, 18), tr("Move"))
        for text, where in ((tr("Move to top"), "top"), (tr("Move up"), "up"),
                            (tr("Move down"), "down"), (tr("Move to bottom"), "bottom")):
            action = QAction(text, order_menu)
            action.triggered.connect(lambda _checked=False, w=where: self._move(order_ids, w))
            order_menu.addAction(action)
        add(tr("Select all"), "check", self._select_all)
        menu.addSeparator()
        add(tr("Remove…"), "trash", lambda: self._remove(order_ids))
        menu.exec(pos)

    def _cancel(self, ids: list[int]) -> None:
        if ids and self.confirm(tr("Cancel download"),
                                tr("Cancel the selected download(s)? The partial data will be deleted."), destructive=True):
            self._controller.cancel(ids)

    def choose_removal(self, records: list[DownloadRecord]) -> str | None:
        """Pergunta o que apagar: «list» (só da lista), «files» (lista e ficheiros) ou None (cancelar)."""
        names = "\n".join(r.filename for r in records[:6])
        if len(records) > 6:
            names += "\n" + tr("…and {count} more.").format(count=len(records) - 6)
        text = tr("Remove {count} download(s)?").format(count=len(records)) + "\n\n" + names + "\n\n" + tr(
            "Choose whether to remove them only from the list or also delete the downloaded files from disk. "
            "Deleting files cannot be undone."
        )
        if any(r.status.is_pending for r in records):
            text += "\n\n" + tr("Some downloads are not finished. Removing them stops the transfer.")
        box = QMessageBox(QMessageBox.Icon.Question, tr("Remove from list"), text, parent=self)
        only_list = box.addButton(tr("Remove from list only"), QMessageBox.ButtonRole.AcceptRole)
        with_files = box.addButton(tr("Remove and delete files"), QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(tr("Cancel"), QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(only_list)
        box.exec()
        if box.clickedButton() is only_list:
            return "list"
        if box.clickedButton() is with_files:
            return "files"
        return None

    def _remove(self, ids: list[int]) -> None:
        records = self._records_for(ids)
        if not records:
            return
        choice = self.choose_removal(records)
        valid = [r.id for r in records if r.id is not None]
        if choice == "list":
            self._controller.remove(valid)
        elif choice == "files":
            self._controller.delete_files(valid)

    def _sorted_notice(self) -> bool:
        """Durante uma ordenação por coluna não se reordena à mão; avisa em vez de falhar em silêncio."""
        if self.page.proxy.is_sorted:
            self.statusBar().showMessage(
                tr("The list is sorted by a column. Click the column title until the arrow disappears to reorder manually."),
                6000,
            )
            return True
        return False

    def _on_rows_moved(self, ids: list[int], target: object, after: bool) -> None:
        if not self._sorted_notice():
            self._controller.move_to(ids, target, after)

    def _move(self, ids: list[int], where: str) -> None:
        if ids and not self._sorted_notice():
            self._controller.move(ids, where)

    def _select_all(self) -> None:
        focused = QApplication.focusWidget()
        if isinstance(focused, QLineEdit):
            focused.selectAll()
        else:
            self.page.view.selectAll()

    def _on_selection_changed(self) -> None:
        self.delete_button.setEnabled(bool(self.page.selected_ids()))

    def _apply_browser_integration(self) -> None:
        s = self._settings
        self._bridge.apply(s.browser_integration, s.browser_port, s.browser_token)

    def _on_browser_links(self, links: list[str], extra: dict[str, str]) -> None:
        """Links enviados pela extensão (o navegador já cancelou o seu próprio download).

        Com «perguntar antes de adicionar» ligado abrem o diálogo; caso contrário entram diretamente
        na pasta predefinida. Nunca se perdem: se o diálogo estiver aberto, ficam em fila.
        """
        if self._add_dialog_open:
            self._browser_queue.append((links, extra))
            return
        context = RequestContext(extra.get("referer", ""), extra.get("user_agent", ""), extra.get("cookies", ""))
        if self._settings.browser_confirm:
            if self.isMinimized():
                self.showNormal()
            self.raise_()
            self.activateWindow()
            self.add_download("\n".join(links), context)
            return
        self._controller.add(links, self._settings.download_dir, filename=extra.get("filename", ""), context=context)
        self.statusBar().showMessage(tr("Download received from the browser."), 4000)

    def bring_to_front(self) -> None:
        if self.isMinimized():
            self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()

    def _on_pair_requested(self, _origin: str) -> None:
        """A extensão pede o token: só é entregue se o utilizador confirmar aqui."""
        if self.isMinimized():
            self.showNormal()
        self.raise_()
        self.activateWindow()
        answer = QMessageBox.question(
            self, tr("Browser integration"), tr("Allow the browser extension to send downloads to Nova DM?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        self._bridge.answer_pair(answer == QMessageBox.StandardButton.Yes)

    def _drain_browser_queue(self) -> None:
        if self._add_dialog_open or not self._browser_queue:
            return
        links, extra = self._browser_queue.pop(0)
        self._on_browser_links(links, extra)

    def _on_links_dropped(self, links: list[str]) -> None:
        self.add_download("\n".join(links))

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if dropped_links(event.mimeData()):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        links = dropped_links(event.mimeData())
        if links:
            event.acceptProposedAction()
            self._on_links_dropped(links)
        else:
            super().dropEvent(event)

    def _delete_files(self, ids: list[int]) -> None:
        records = self._records_for(ids)
        if not records:
            return
        if self._settings.confirm_delete:
            names = "\n".join(r.filename for r in records[:6])
            more = tr("…and {count} more.").format(count=len(records) - 6) if len(records) > 6 else ""
            text = tr("Delete these files from disk and remove them from the list? This cannot be undone.")
            if not self.confirm(tr("Delete file from disk"), f"{text}\n\n{names}\n{more}".strip(), destructive=True):
                return
        self._controller.delete_files([r.id for r in records if r.id is not None])

    def _show_details(self, download_id: int | None) -> None:
        record = self._records.get(download_id or -1)
        if record is not None:
            DetailsDialog(record, self).exec()

    def _open_folder(self, download_id: int | None) -> None:
        record = self._records.get(download_id or -1)
        if record is None:
            return
        folder = Path(record.directory)
        if not folder.is_dir():
            self.show_error(tr("The folder no longer exists: {path}").format(path=folder))
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _open_file(self, download_id: int | None) -> None:
        record = self._records.get(download_id or -1)
        if record is None:
            return
        path = Path(record.path)
        if not path.is_file():
            self.show_error(tr("The file no longer exists: {path}").format(path=path))
            return
        if record.category == "program" and not self.confirm(
            tr("Open file"),
            tr("This looks like a program or installer. Only open it if you trust where it came from.\n\n"
               "Open it with the default application?"),
            destructive=True,
        ):
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    # Definições ----------------------------------------------------------

    def _on_settings_saved(self, settings: Settings) -> None:
        theme_changed = settings.theme != self._settings.theme
        self._settings = settings
        settings.save(self._repo)
        self._controller.apply_settings(settings)
        self._apply_browser_integration()
        if theme_changed:
            app = QApplication.instance()
            if isinstance(app, QApplication):
                apply_theme(app, settings.theme)
            self._refresh_theme_icons()
            self.page.view.viewport().update()
            self.page.header.update()

    # Encerramento --------------------------------------------------------

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        if self._shutting_down:
            event.accept()
            return
        running = sum(r.status in _PENDING for r in self._records.values())
        if running and not self._closing_confirmed:
            ok = self.confirm(
                tr("Quit Nova DM"),
                tr("{count} download(s) are in progress. They will be paused and resumed the next time you open the app. "
                   "Quit now?").format(count=running),
            )
            if not ok:
                event.ignore()
                return
        self._closing_confirmed = True
        self._shutting_down = True
        # Parar o motor pode demorar alguns segundos: esconder a janela já, para o clique em «fechar» ter efeito imediato.
        self.hide()
        QApplication.processEvents()
        self._bridge.stop()
        self._controller.shutdown()
        event.accept()
