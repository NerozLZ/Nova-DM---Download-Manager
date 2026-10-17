"""Modelo Qt da lista de downloads e respetivo filtro."""

from __future__ import annotations

from PySide6.QtCore import QAbstractListModel, QModelIndex, QObject, QSortFilterProxyModel, Qt

from nova_dm.core.models import DownloadRecord, DownloadStatus

RecordRole = Qt.ItemDataRole.UserRole + 1

# Filtros da barra lateral -> estados aceites
STATUS_FILTERS: dict[str, frozenset[DownloadStatus]] = {
    "active": frozenset({DownloadStatus.ACTIVE}),
    "queued": frozenset({DownloadStatus.QUEUED}),
    "completed": frozenset({DownloadStatus.COMPLETED}),
    "stopped": frozenset({DownloadStatus.PAUSED, DownloadStatus.CANCELLED}),
    "failed": frozenset({DownloadStatus.FAILED}),
    "history": frozenset({DownloadStatus.COMPLETED, DownloadStatus.FAILED, DownloadStatus.CANCELLED}),
}


class DownloadModel(QAbstractListModel):
    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._records: list[DownloadRecord] = []

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008, N802
        return 0 if parent.isValid() else len(self._records)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if not index.isValid() or not 0 <= index.row() < len(self._records):
            return None
        record = self._records[index.row()]
        if role == RecordRole:
            return record
        if role == Qt.ItemDataRole.DisplayRole:
            return record.filename
        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:  # noqa: N802
        base = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        return base | Qt.ItemFlag.ItemIsDragEnabled if index.isValid() else base

    def set_records(self, records: list[DownloadRecord]) -> None:
        """Atualiza o modelo de forma incremental (mantém seleção e posição de scroll)."""
        incoming = sorted(records, key=lambda r: (r.position, r.id or 0))
        incoming_ids = {r.id for r in incoming}

        for row in range(len(self._records) - 1, -1, -1):
            if self._records[row].id not in incoming_ids:
                self.beginRemoveRows(QModelIndex(), row, row)
                del self._records[row]
                self.endRemoveRows()

        known = {r.id for r in self._records}
        for position, record in enumerate(incoming):
            if record.id not in known:
                self.beginInsertRows(QModelIndex(), position, position)
                self._records.insert(position, record)
                self.endInsertRows()

        self._reorder([r.id for r in incoming])

        for row, record in enumerate(incoming):
            if self._records[row] != record:
                self._records[row] = record
                index = self.index(row)
                self.dataChanged.emit(index, index)

    def _reorder(self, wanted: list[int | None]) -> None:
        """Muda a ordem das linhas sem perder a seleção (usa índices persistentes)."""
        if [r.id for r in self._records] == wanted:
            return
        self.layoutAboutToBeChanged.emit()
        persistent = self.persistentIndexList()
        old_ids = [self._records[i.row()].id for i in persistent]
        by_id = {r.id: r for r in self._records}
        self._records = [by_id[i] for i in wanted]
        new_rows = {r.id: row for row, r in enumerate(self._records)}
        self.changePersistentIndexList(persistent, [self.index(new_rows[i]) for i in old_ids])
        self.layoutChanged.emit()

    def all_records(self) -> list[DownloadRecord]:
        return list(self._records)


_STATUS_ORDER = {s: i for i, s in enumerate((
    DownloadStatus.ACTIVE, DownloadStatus.QUEUED, DownloadStatus.PAUSED,
    DownloadStatus.COMPLETED, DownloadStatus.FAILED, DownloadStatus.CANCELLED,
))}


def sort_key(column: str, record: DownloadRecord) -> tuple:
    """Chave de ordenação de cada coluna (a mesma ordem que o utilizador vê)."""
    name = record.filename.casefold()
    if column == "name":
        return (name,)
    if column == "size":
        return (record.total_bytes, name)  # tamanho desconhecido conta como 0 (primeiro, em ordem crescente)
    if column == "type":
        extension = name.rsplit(".", 1)[1] if "." in name.strip(".") else ""
        return (extension, record.category, name)
    if column == "progress":
        return (record.progress, name)
    if column == "status":
        return (_STATUS_ORDER[record.status], name)
    if column == "speed":
        return (record.download_speed, name)
    if column == "eta":
        eta = record.eta_seconds
        return (eta is None, eta or 0, name)
    raise ValueError(f"Coluna desconhecida: {column}")


class DownloadFilterProxy(QSortFilterProxyModel):
    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.sort_column: str | None = None
        self.sort_ascending = True
        self._statuses: frozenset[DownloadStatus] | None = None
        self._category: str | None = None
        self._text = ""

    def set_filter_key(self, key: str) -> None:
        """«all», um filtro de estado, ou «cat:<categoria>»."""
        self._statuses = None
        self._category = None
        if key.startswith("cat:"):
            self._category = key[4:]
        elif key in STATUS_FILTERS:
            self._statuses = STATUS_FILTERS[key]
        self.invalidateFilter()

    @property
    def is_sorted(self) -> bool:
        return self.sort_column is not None

    def set_sort(self, column: str | None, ascending: bool = True) -> None:
        """Ordena por coluna; `None` volta à ordem manual (a da fila)."""
        self.sort_column = column
        self.sort_ascending = ascending
        if column is None:
            self.sort(-1)
        else:
            self.sort(0, Qt.SortOrder.AscendingOrder if ascending else Qt.SortOrder.DescendingOrder)
        self.invalidate()

    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:  # noqa: N802
        if self.sort_column is None:
            return left.row() < right.row()
        a, b = left.data(RecordRole), right.data(RecordRole)
        if not isinstance(a, DownloadRecord) or not isinstance(b, DownloadRecord):
            return False
        return sort_key(self.sort_column, a) < sort_key(self.sort_column, b)

    def set_search_text(self, text: str) -> None:
        self._text = text.strip().casefold()
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:  # noqa: N802
        record = self.sourceModel().index(source_row, 0, source_parent).data(RecordRole)
        if not isinstance(record, DownloadRecord):
            return False
        if self._statuses is not None and record.status not in self._statuses:
            return False
        if self._category is not None and record.category != self._category:
            return False
        return not self._text or self._text in record.filename.casefold() or self._text in record.url.casefold()
