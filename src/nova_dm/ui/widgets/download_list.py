"""Lista de downloads: cabeçalho de colunas, vista e delegate que desenha cada cartão."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QItemSelectionModel, QMimeData, QModelIndex, QPoint, QPointF, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QDrag,
    QDragEnterEvent,
    QDragMoveEvent,
    QDropEvent,
    QFont,
    QFontMetrics,
    QMouseEvent,
    QPainter,
    QPen,
    QPolygonF,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QListView,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QToolTip,
    QWidget,
)

from nova_dm.core.models import DownloadRecord, DownloadStatus
from nova_dm.i18n import tr
from nova_dm.ui import icons
from nova_dm.ui.download_model import RecordRole
from nova_dm.ui.presentation import category_label, progress_color, status_color, status_label
from nova_dm.ui.styles import current_palette
from nova_dm.ui.widgets.download_layout import (
    BUTTON_GAP,
    BUTTON_SIZE,
    CARD_HEIGHT,
    CARD_MARGIN_X,
    CARD_MARGIN_Y,
    CHECK_SIZE,
    CHECK_X,
    ICON_SIZE,
    Columns,
    compute_columns,
)
from nova_dm.utils.formatting import format_eta, format_size, format_speed
from nova_dm.utils.urls import extract_urls

IDS_MIME = "application/x-novadm-download-ids"


def check_rect(card: QRect) -> QRect:
    return QRect(card.left() + CHECK_X, card.top() + (card.height() - CHECK_SIZE) // 2, CHECK_SIZE, CHECK_SIZE)


def dropped_links(mime: QMimeData) -> list[str]:
    """Links http(s) de um arrastar-e-largar vindo de fora (browser, editor de texto…)."""
    candidates = [url.toString() for url in mime.urls()] if mime.hasUrls() else []
    if mime.hasText():
        candidates.append(mime.text())
    return extract_urls("\n".join(candidates))


def paint_checkbox(painter: QPainter, rect: QRect, state: Qt.CheckState, palette, hot: bool = False) -> None:  # noqa: ANN001
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    box = QRectF(rect).adjusted(0.5, 0.5, -0.5, -0.5)
    checked = state is not Qt.CheckState.Unchecked
    painter.setPen(QPen(QColor(palette.accent if (checked or hot) else palette.text_faint), 1.4))
    painter.setBrush(QColor(palette.accent) if checked else Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(box, 5, 5)
    if checked:
        painter.setPen(QPen(QColor("#ffffff"), 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        cx, cy = box.center().x(), box.center().y()
        if state is Qt.CheckState.PartiallyChecked:
            painter.drawLine(int(cx - 4), int(cy), int(cx + 4), int(cy))
        else:
            painter.drawPolyline([QPoint(int(cx - 4), int(cy)), QPoint(int(cx - 1), int(cy + 3)), QPoint(int(cx + 4), int(cy - 3))])
    painter.restore()


def primary_action(status: DownloadStatus) -> tuple[str, str]:
    """(nome do ícone, ação) do botão principal de cada estado."""
    return {
        DownloadStatus.ACTIVE: ("pause", "pause"),
        DownloadStatus.QUEUED: ("pause", "pause"),
        DownloadStatus.PAUSED: ("play", "resume"),
        DownloadStatus.FAILED: ("retry", "retry"),
        DownloadStatus.CANCELLED: ("retry", "retry"),
        DownloadStatus.COMPLETED: ("file", "open"),
    }[status]


class DownloadListView(QListView):
    """Lista com seleção múltipla, caixas de seleção, arrastar para reordenar e largar links."""

    rows_moved = Signal(list, object, bool)  # ids, id de destino (ou None = fim), depois?
    links_dropped = Signal(list)  # URLs largados vindos de fora

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.hover_pos: QPoint | None = None
        self._drop_line: int | None = None  # y do indicador de largada
        self.reorder_enabled = True  # falso quando a lista está ordenada por coluna
        self.setMouseTracking(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QListView.Shape.NoFrame)
        self.setUniformItemSizes(True)
        self.verticalScrollBar().setSingleStep(24)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(False)  # o indicador é desenhado por nós (paintEvent)

    # Caixas de seleção -----------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position().toPoint()
            index = self.indexAt(pos)
            if index.isValid():
                card = DownloadDelegate.card_rect(self.visualRect(index))
                if check_rect(card).adjusted(-6, -6, 6, 6).contains(pos):
                    self.selectionModel().select(index, QItemSelectionModel.SelectionFlag.Toggle)
                    self.selectionModel().setCurrentIndex(index, QItemSelectionModel.SelectionFlag.NoUpdate)
                    event.accept()
                    return
        super().mousePressEvent(event)

    def select_all_rows(self) -> None:
        self.selectAll()

    def check_state(self) -> Qt.CheckState:
        total = self.model().rowCount() if self.model() else 0
        chosen = len(self.selectionModel().selectedRows()) if self.selectionModel() else 0
        if chosen == 0 or total == 0:
            return Qt.CheckState.Unchecked
        return Qt.CheckState.Checked if chosen >= total else Qt.CheckState.PartiallyChecked

    # Arrastar para reordenar -----------------------------------------

    def startDrag(self, supported_actions: Qt.DropAction) -> None:  # noqa: N802
        ids = []
        for index in self.selectionModel().selectedRows():
            record = index.data(RecordRole)
            if isinstance(record, DownloadRecord) and record.id is not None:
                ids.append(record.id)
        if not ids:
            return
        mime = QMimeData()
        mime.setData(IDS_MIME, ",".join(map(str, ids)).encode())
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.MoveAction)

    def _target_for(self, pos: QPoint) -> tuple[int | None, bool, int]:
        """(id de destino, depois?, y da linha) para uma posição do rato."""
        index = self.indexAt(pos)
        if not index.isValid():
            last = self.model().rowCount() - 1
            if last < 0:
                return None, False, 0
            rect = self.visualRect(self.model().index(last, 0))
            return None, False, rect.bottom()
        rect = self.visualRect(index)
        after = pos.y() > rect.center().y()
        record = index.data(RecordRole)
        target = record.id if isinstance(record, DownloadRecord) else None
        return target, after, rect.bottom() if after else rect.top()

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if event.mimeData().hasFormat(IDS_MIME) or dropped_links(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:  # noqa: N802
        if event.mimeData().hasFormat(IDS_MIME):
            if self.reorder_enabled:
                self._drop_line = self._target_for(event.position().toPoint())[2]
                self.viewport().update()
            event.acceptProposedAction()
        elif dropped_links(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event) -> None:  # noqa: ANN001, N802
        self._drop_line = None
        self.viewport().update()
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        self._drop_line = None
        self.viewport().update()
        mime = event.mimeData()
        if mime.hasFormat(IDS_MIME):
            ids = [int(part) for part in bytes(mime.data(IDS_MIME)).decode().split(",") if part.isdigit()]
            target, after, _ = self._target_for(event.position().toPoint())
            if ids:
                self.rows_moved.emit(ids, target, after)
            event.acceptProposedAction()
            return
        links = dropped_links(mime)
        if links:
            self.links_dropped.emit(links)
            event.acceptProposedAction()
        else:
            event.ignore()

    def paintEvent(self, event) -> None:  # noqa: ANN001, N802
        super().paintEvent(event)
        if self._drop_line is not None:
            painter = QPainter(self.viewport())
            painter.setPen(QPen(QColor(current_palette().accent_2), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            y = self._drop_line
            painter.drawLine(CARD_MARGIN_X + 4, y, self.viewport().width() - CARD_MARGIN_X - 4, y)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self.hover_pos = event.position().toPoint()
        self.viewport().update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event: QEvent) -> None:  # noqa: N802
        self.hover_pos = None
        self.viewport().update()
        super().leaveEvent(event)


class DownloadDelegate(QStyledItemDelegate):
    primary_clicked = Signal(int, str)  # id, ação
    menu_requested = Signal(int, QPoint)  # id, posição global

    def __init__(self, view: DownloadListView) -> None:
        super().__init__(view)
        self._view = view
        self._name_font = QFont()
        self._name_font.setPointSizeF(10)
        self._name_font.setWeight(QFont.Weight.DemiBold)
        self._small_font = QFont()
        self._small_font.setPointSizeF(9.5)

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:  # noqa: N802
        return QSize(option.rect.width(), CARD_HEIGHT)

    # Geometria ---------------------------------------------------------

    @staticmethod
    def card_rect(row_rect: QRect) -> QRect:
        return row_rect.adjusted(CARD_MARGIN_X, CARD_MARGIN_Y, -CARD_MARGIN_X, -CARD_MARGIN_Y)

    @staticmethod
    def _button_rects(card: QRect, cols: Columns) -> tuple[QRect, QRect]:
        top = card.top() + (card.height() - BUTTON_SIZE) // 2
        first = QRect(card.left() + cols.actions_x, top, BUTTON_SIZE, BUTTON_SIZE)
        second = QRect(first.right() + 1 + BUTTON_GAP, top, BUTTON_SIZE, BUTTON_SIZE)
        return first, second

    # Desenho -----------------------------------------------------------

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        record = index.data(RecordRole)
        if not isinstance(record, DownloadRecord):
            return
        p = current_palette()
        card = self.card_rect(option.rect)
        cols = compute_columns(card.width())
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        background = p.card_selected if selected else (p.card_hover if hovered else p.card)
        border = p.accent if selected else p.border
        painter.setPen(QPen(QColor(border), 1))
        painter.setBrush(QBrush(QColor(background)))
        painter.drawRoundedRect(QRectF(card).adjusted(0.5, 0.5, -0.5, -0.5), 14, 14)

        paint_checkbox(painter, check_rect(card), Qt.CheckState.Checked if selected else Qt.CheckState.Unchecked, p,
                       hot=self._view.hover_pos is not None and check_rect(card).contains(self._view.hover_pos))
        self._paint_file_icon(painter, card, record)
        self._paint_name(painter, card, cols, record, p)
        self._paint_size_and_type(painter, card, cols, record, p)
        self._paint_progress(painter, card, cols, record, p)
        self._paint_texts(painter, card, cols, record, p)
        self._paint_buttons(painter, card, cols, record, p)
        painter.restore()

    def _paint_file_icon(self, painter: QPainter, card: QRect, record: DownloadRecord) -> None:
        color, glyph = icons.CATEGORY_STYLE.get(record.category, icons.CATEGORY_STYLE["other"])
        box = QRect(card.left() + CHECK_X + CHECK_SIZE + 12, card.top() + (card.height() - ICON_SIZE) // 2, ICON_SIZE, ICON_SIZE)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(color))
        painter.drawRoundedRect(box, 11, 11)
        size = 22
        dpr = self._view.devicePixelRatioF()
        pix = icons.pixmap(glyph, "#ffffff", size, dpr)
        painter.drawPixmap(box.left() + (ICON_SIZE - size) // 2, box.top() + (ICON_SIZE - size) // 2, pix)

    def _paint_name(self, painter: QPainter, card: QRect, cols: Columns, record: DownloadRecord, p) -> None:  # noqa: ANN001
        painter.setFont(self._name_font)
        painter.setPen(QColor(p.text))
        metrics = QFontMetrics(self._name_font)
        rect = QRect(card.left() + cols.name_x, card.top(), cols.name_w, card.height())
        painter.drawText(rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                         metrics.elidedText(record.filename, Qt.TextElideMode.ElideMiddle, cols.name_w))

    def _paint_size_and_type(self, painter: QPainter, card: QRect, cols: Columns, record: DownloadRecord, p) -> None:  # noqa: ANN001
        align = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        painter.setFont(self._small_font)
        if cols.size_w:
            known = record.total_bytes > 0
            text = format_size(record.total_bytes) if known else "—"
            painter.setPen(QColor(p.text if known else p.text_faint))
            painter.drawText(QRect(card.left() + cols.size_x, card.top(), cols.size_w, card.height()), align, text)
        if cols.type_w:
            suffix = record.filename.rsplit(".", 1)[1].upper() if "." in record.filename.strip(".") else ""
            upper = QRect(card.left() + cols.type_x, card.top() + 16, cols.type_w, 20)
            lower = QRect(card.left() + cols.type_x, card.top() + 36, cols.type_w, 20)
            metrics = QFontMetrics(self._small_font)
            painter.setPen(QColor(p.text))
            painter.drawText(upper, align, metrics.elidedText(suffix or "—", Qt.TextElideMode.ElideRight, cols.type_w))
            painter.setPen(QColor(p.text_muted))
            painter.drawText(lower, align, metrics.elidedText(category_label(record.category), Qt.TextElideMode.ElideRight, cols.type_w))

    def _paint_progress(self, painter: QPainter, card: QRect, cols: Columns, record: DownloadRecord, p) -> None:  # noqa: ANN001
        if not cols.progress_w:
            return
        x = card.left() + cols.progress_x
        percent = int(record.progress * 100)
        painter.setFont(self._small_font)
        painter.setPen(QColor(p.text))
        painter.drawText(QRect(x, card.top() + 12, cols.progress_w, 20),
                         Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, f"{percent}%")
        track = QRectF(x, card.top() + 40, cols.progress_w, 6)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(p.track))
        painter.drawRoundedRect(track, 3, 3)
        if percent > 0:
            fill = QRectF(track.left(), track.top(), max(6.0, track.width() * record.progress), track.height())
            painter.setBrush(QColor(progress_color(p, record.status)))
            painter.drawRoundedRect(fill, 3, 3)

    def _paint_texts(self, painter: QPainter, card: QRect, cols: Columns, record: DownloadRecord, p) -> None:  # noqa: ANN001
        painter.setFont(self._small_font)
        mid = QRect(0, card.top(), 0, card.height())
        align = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft

        if cols.speed_w:
            active = record.status is DownloadStatus.ACTIVE and record.download_speed > 0
            painter.setPen(QColor(p.accent_2 if active else p.text_faint))
            text = format_speed(record.download_speed) if active else "—"
            painter.drawText(QRect(card.left() + cols.speed_x, mid.top(), cols.speed_w, mid.height()), align, text)

        if cols.status_w:
            painter.setPen(QColor(status_color(p, record.status)))
            status_rect = QRect(card.left() + cols.status_x, mid.top(), cols.status_w, mid.height())
            painter.drawText(status_rect, align, status_label(record.status))

        if cols.eta_w:
            painter.setPen(QColor(p.text_muted))
            text = format_eta(record.eta_seconds) if record.status is DownloadStatus.ACTIVE else "—"
            painter.drawText(QRect(card.left() + cols.eta_x, mid.top(), cols.eta_w, mid.height()), align, text)

    def _paint_buttons(self, painter: QPainter, card: QRect, cols: Columns, record: DownloadRecord, p) -> None:  # noqa: ANN001
        first, second = self._button_rects(card, cols)
        hover = self._view.hover_pos
        icon_name, _ = primary_action(record.status)
        dpr = self._view.devicePixelRatioF()
        for rect, name in ((first, icon_name), (second, "dots")):
            hot = hover is not None and rect.contains(hover)
            painter.setPen(QPen(QColor(p.accent if hot else p.border), 1))
            painter.setBrush(QColor(p.card_selected if hot else p.panel))
            painter.drawRoundedRect(QRectF(rect).adjusted(0.5, 0.5, -0.5, -0.5), 10, 10)
            size = 18
            pix = icons.pixmap(name, p.text, size, dpr)
            painter.drawPixmap(rect.left() + (rect.width() - size) // 2, rect.top() + (rect.height() - size) // 2, pix)

    # Interação ---------------------------------------------------------

    def editorEvent(self, event: QEvent, model, option: QStyleOptionViewItem, index: QModelIndex) -> bool:  # noqa: ANN001, N802
        if event.type() != QEvent.Type.MouseButtonRelease:
            return super().editorEvent(event, model, option, index)
        mouse = event  # type: ignore[assignment]
        if mouse.button() != Qt.MouseButton.LeftButton:  # type: ignore[attr-defined]
            return False
        record = index.data(RecordRole)
        if not isinstance(record, DownloadRecord) or record.id is None:
            return False
        card = self.card_rect(option.rect)
        first, second = self._button_rects(card, compute_columns(card.width()))
        pos = mouse.position().toPoint()  # type: ignore[attr-defined]
        if first.contains(pos):
            self.primary_clicked.emit(record.id, primary_action(record.status)[1])
            return True
        if second.contains(pos):
            self.menu_requested.emit(record.id, self._view.viewport().mapToGlobal(second.bottomLeft()))
            return True
        return False

    def helpEvent(self, event, view, option: QStyleOptionViewItem, index: QModelIndex) -> bool:  # noqa: ANN001, N802
        record = index.data(RecordRole)
        if isinstance(record, DownloadRecord):
            text = record.error_message if record.status is DownloadStatus.FAILED and record.error_message else record.url
            QToolTip.showText(event.globalPos(), text, view)
            return True
        return super().helpEvent(event, view, option, index)


class ColumnHeader(QWidget):
    """Linha de títulos alinhada com as colunas dos cartões, com a caixa «selecionar tudo»."""

    select_all_clicked = Signal()
    sort_requested = Signal(str)  # chave da coluna

    COLUMN_KEYS = ("name", "size", "type", "progress", "status", "speed", "eta")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(36)
        self.setMouseTracking(True)
        self.right_margin = 0  # compensação da barra de scroll
        self.check_state = Qt.CheckState.Unchecked
        self.sort_column: str | None = None
        self.sort_ascending = True
        self._hover: str | None = None

    def set_sort(self, column: str | None, ascending: bool) -> None:
        self.sort_column, self.sort_ascending = column, ascending
        self.update()

    def _column_rects(self) -> dict[str, QRect]:
        cols = compute_columns(self.width() - 2 * CARD_MARGIN_X - self.right_margin)
        spans = zip(self.COLUMN_KEYS, (
            (cols.name_x, cols.name_w), (cols.size_x, cols.size_w), (cols.type_x, cols.type_w),
            (cols.progress_x, cols.progress_w), (cols.status_x, cols.status_w),
            (cols.speed_x, cols.speed_w), (cols.eta_x, cols.eta_w),
        ), strict=True)
        return {key: QRect(CARD_MARGIN_X + x - 4, 0, w + 4, self.height()) for key, (x, w) in spans if w}

    def _column_at(self, pos: QPoint) -> str | None:
        return next((key for key, rect in self._column_rects().items() if rect.contains(pos)), None)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        key = self._column_at(event.position().toPoint())
        if key != self._hover:
            self._hover = key
            self.setCursor(Qt.CursorShape.PointingHandCursor if key else Qt.CursorShape.ArrowCursor)
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event: QEvent) -> None:  # noqa: N802
        self._hover = None
        self.unsetCursor()
        self.update()
        super().leaveEvent(event)

    def set_check_state(self, state: Qt.CheckState) -> None:
        if state != self.check_state:
            self.check_state = state
            self.update()

    def _check_rect(self) -> QRect:
        return QRect(CARD_MARGIN_X + CHECK_X, (self.height() - CHECK_SIZE) // 2, CHECK_SIZE, CHECK_SIZE)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._check_rect().adjusted(-6, -6, 6, 6).contains(event.position().toPoint()):
            self.select_all_clicked.emit()
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            key = self._column_at(event.position().toPoint())
            if key:
                self.sort_requested.emit(key)
                event.accept()
                return
        super().mousePressEvent(event)

    def paintEvent(self, event) -> None:  # noqa: ANN001, N802
        p = current_palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        paint_checkbox(painter, self._check_rect(), self.check_state, p)
        font = QFont(self.font())
        font.setPointSizeF(9.5)
        painter.setFont(font)
        painter.setPen(QColor(p.text_muted))
        card_width = self.width() - 2 * CARD_MARGIN_X - self.right_margin
        cols = compute_columns(card_width)
        left = CARD_MARGIN_X
        align = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        labels = (tr("File name"), tr("Size"), tr("Type"), tr("Progress"), tr("Status"), tr("Speed"), tr("Time left"))
        spans = ((cols.name_x, cols.name_w), (cols.size_x, cols.size_w), (cols.type_x, cols.type_w),
                 (cols.progress_x, cols.progress_w), (cols.status_x, cols.status_w),
                 (cols.speed_x, cols.speed_w), (cols.eta_x, cols.eta_w))
        metrics = QFontMetrics(font)
        for key, (x, w), label in zip(self.COLUMN_KEYS, spans, labels, strict=True):
            if not w:
                continue
            active = key == self.sort_column
            painter.setPen(QColor(p.text if (active or key == self._hover) else p.text_muted))
            room = w - (14 if active else 0)
            text = metrics.elidedText(label, Qt.TextElideMode.ElideRight, room)
            painter.drawText(QRectF(left + x, 0, room, self.height()), align, text)
            if active:
                ax = left + x + min(metrics.horizontalAdvance(text), room) + 7
                cy = self.height() / 2
                up = self.sort_ascending
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                painter.setBrush(QColor(p.accent_2))
                painter.setPen(Qt.PenStyle.NoPen)
                tri = [QPointF(ax - 4, cy + 2), QPointF(ax + 4, cy + 2), QPointF(ax, cy - 3)] if up else \
                      [QPointF(ax - 4, cy - 2), QPointF(ax + 4, cy - 2), QPointF(ax, cy + 3)]
                painter.drawPolygon(QPolygonF(tri))
