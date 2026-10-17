"""Página principal: cabeçalho de colunas + lista de cartões (ou mensagem de lista vazia)."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QModelIndex, QPoint, Qt, Signal
from PySide6.QtWidgets import QFrame, QLabel, QStackedLayout, QVBoxLayout, QWidget

from nova_dm.core.models import DownloadRecord
from nova_dm.i18n import tr
from nova_dm.ui.download_model import DownloadFilterProxy, DownloadModel, RecordRole
from nova_dm.ui.widgets.download_list import ColumnHeader, DownloadDelegate, DownloadListView


class DownloadsPage(QFrame):
    primary_clicked = Signal(int, str)
    menu_requested = Signal(int, QPoint)
    context_menu_requested = Signal(QPoint)
    open_requested = Signal(int)
    rows_moved = Signal(list, object, bool)  # ids, destino (ou None), depois?
    links_dropped = Signal(list)
    selection_changed = Signal()
    sort_changed = Signal()

    def __init__(self, model: DownloadModel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Panel")
        self.proxy = DownloadFilterProxy(self)
        self.proxy.setSourceModel(model)

        self.view = DownloadListView()
        self.view.setModel(self.proxy)
        self.delegate = DownloadDelegate(self.view)
        self.view.setItemDelegate(self.delegate)
        self.view.viewport().installEventFilter(self)
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self._on_context_menu)
        self.view.doubleClicked.connect(self._on_double_click)
        self.delegate.primary_clicked.connect(self.primary_clicked)
        self.delegate.menu_requested.connect(self.menu_requested)
        self.view.rows_moved.connect(self.rows_moved)
        self.view.links_dropped.connect(self.links_dropped)
        self.view.selectionModel().selectionChanged.connect(lambda *_: self._on_selection())

        self.header = ColumnHeader()
        self.header.select_all_clicked.connect(self.toggle_select_all)
        self.header.sort_requested.connect(self.cycle_sort)
        self._empty = QLabel(tr("No downloads here yet.\nPress the + button or Ctrl+V to add a link."))
        self._empty.setObjectName("Muted")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)

        holder = QWidget()
        self._stack = QStackedLayout(holder)
        self._stack.addWidget(self.view)
        self._stack.addWidget(self._empty)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 8)
        layout.setSpacing(0)
        layout.addWidget(self.header)
        layout.addWidget(holder, 1)

        for signal in (self.proxy.rowsInserted, self.proxy.rowsRemoved, self.proxy.modelReset, self.proxy.layoutChanged):
            signal.connect(self._refresh_empty_state)
            signal.connect(self._on_selection)
        self._refresh_empty_state()

    def cycle_sort(self, column: str) -> None:
        """Clicar numa coluna: crescente → decrescente → ordem manual."""
        proxy = self.proxy
        if proxy.sort_column != column:
            proxy.set_sort(column, True)
        elif proxy.sort_ascending:
            proxy.set_sort(column, False)
        else:
            proxy.set_sort(None)
        self.header.set_sort(proxy.sort_column, proxy.sort_ascending)
        self.view.reorder_enabled = not proxy.is_sorted
        self.sort_changed.emit()

    def toggle_select_all(self) -> None:
        if self.view.check_state() is Qt.CheckState.Checked:
            self.view.clearSelection()
        else:
            self.view.selectAll()

    def _on_selection(self) -> None:
        self.header.set_check_state(self.view.check_state())
        self.selection_changed.emit()

    def _refresh_empty_state(self) -> None:
        self._stack.setCurrentWidget(self.view if self.proxy.rowCount() else self._empty)

    def _sync_header(self) -> None:
        """Alinha o cabeçalho com os cartões: compensa a largura real da barra de scroll."""
        self.header.right_margin = max(0, self.view.width() - self.view.viewport().width())
        self.header.update()

    def eventFilter(self, watched, event) -> bool:  # noqa: ANN001, N802
        if watched is self.view.viewport() and event.type() == QEvent.Type.Resize:
            self._sync_header()
        return super().eventFilter(watched, event)

    def resizeEvent(self, event) -> None:  # noqa: ANN001, N802
        super().resizeEvent(event)
        self._sync_header()

    def selected_ids(self) -> list[int]:
        ids: list[int] = []
        for index in self.view.selectionModel().selectedRows():
            record = index.data(RecordRole)
            if isinstance(record, DownloadRecord) and record.id is not None:
                ids.append(record.id)
        return ids

    def _on_context_menu(self, pos: QPoint) -> None:
        index = self.view.indexAt(pos)
        if not index.isValid():
            return
        if not self.view.selectionModel().isSelected(index):
            self.view.setCurrentIndex(index)
        self.context_menu_requested.emit(self.view.viewport().mapToGlobal(pos))

    def _on_double_click(self, index: QModelIndex) -> None:
        record = index.data(RecordRole)
        if isinstance(record, DownloadRecord) and record.id is not None:
            self.open_requested.emit(record.id)

    def select_id(self, download_id: int) -> None:
        for row in range(self.proxy.rowCount()):
            index = self.proxy.index(row, 0)
            record = index.data(RecordRole)
            if isinstance(record, DownloadRecord) and record.id == download_id:
                self.view.setCurrentIndex(index)
                return
