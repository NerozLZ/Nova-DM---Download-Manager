"""Barra lateral de navegação."""

from __future__ import annotations

from PySide6.QtCore import QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QAbstractButton, QButtonGroup, QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from nova_dm import APP_NAME
from nova_dm.i18n import tr
from nova_dm.ui import icons
from nova_dm.ui.presentation import category_label
from nova_dm.ui.styles import current_palette

NAV_ITEMS = (
    ("all", "download"),
    ("active", "progress"),
    ("queued", "queue"),
    ("completed", "check"),
    ("stopped", "pause-circle"),
    ("failed", "alert"),
)


def _nav_label(key: str) -> str:
    return {
        "all": tr("All downloads"),
        "active": tr("In progress"),
        "queued": tr("Queued"),
        "completed": tr("Completed"),
        "stopped": tr("Stopped"),
        "failed": tr("Failed"),
        "settings": tr("Settings"),
    }[key]


class NavItem(QAbstractButton):
    def __init__(self, key: str, label: str, icon_name: str, *, tile_color: str | None = None,
                 show_count: bool = True, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.key = key
        self._label = label
        self._icon_name = icon_name
        self._tile_color = tile_color
        self._show_count = show_count
        self._count = 0
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(42)
        self.setAccessibleName(label)
        self.setToolTip(label)  # texto completo quando o idioma é mais longo do que a barra lateral

    def set_count(self, count: int) -> None:
        if count != self._count:
            self._count = count
            self.update()

    def count(self) -> int:
        return self._count

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(200, 42)

    def paintEvent(self, event) -> None:  # noqa: ANN001, N802
        p = current_palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        hovered = self.underMouse()
        if self.isChecked():
            painter.setPen(QPen(QColor(p.border), 1))
            painter.setBrush(QColor(p.card_selected))
            painter.drawRoundedRect(rect, 12, 12)
        elif hovered:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(p.card_hover))
            painter.drawRoundedRect(rect, 12, 12)

        dpr = self.devicePixelRatioF()
        x = 14
        if self._tile_color:
            tile = QRect(x, (self.height() - 26) // 2, 26, 26)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(self._tile_color))
            painter.drawRoundedRect(tile, 7, 7)
            painter.drawPixmap(tile.left() + 5, tile.top() + 5, icons.pixmap(self._icon_name, "#ffffff", 16, dpr))
            x = tile.right() + 12
        else:
            icon_color = p.accent_2 if self.isChecked() else p.text_muted
            painter.drawPixmap(x, (self.height() - 20) // 2, icons.pixmap(self._icon_name, icon_color, 20, dpr))
            x += 20 + 12

        font = QFont(self.font())
        font.setPointSizeF(10.5)
        painter.setFont(font)
        painter.setPen(QColor(p.text if self.isChecked() or hovered else p.text_muted))
        badge_w = 0
        if self._show_count and self._count >= 0:
            badge_w = 40
        text_rect = QRect(x, 0, self.width() - x - badge_w - 8, self.height())
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                         QFontMetrics(font).elidedText(self._label, Qt.TextElideMode.ElideRight, text_rect.width()))

        if self._show_count:
            badge = QRectF(self.width() - 46, (self.height() - 24) / 2, 36, 24)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(p.badge))
            painter.drawRoundedRect(badge, 8, 8)
            small = QFont(font)
            small.setPointSizeF(9.5)
            painter.setFont(small)
            painter.setPen(QColor(p.text_muted))
            painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, str(self._count))

    def enterEvent(self, event) -> None:  # noqa: ANN001, N802
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: ANN001, N802
        self.update()
        super().leaveEvent(event)


class Sidebar(QWidget):
    """Emite `selected(chave)`; chaves: all, active, queued, completed, stopped, failed, cat:<x>, settings."""

    selected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(264)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._items: dict[str, NavItem] = {}
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 18, 14, 14)
        layout.setSpacing(4)

        layout.addWidget(self._build_brand())
        layout.addSpacing(18)

        for key, icon_name in NAV_ITEMS:
            layout.addWidget(self._add_item(NavItem(key, _nav_label(key), icon_name)))

        layout.addSpacing(14)
        title = QLabel(tr("CATEGORIES"))
        title.setObjectName("SectionTitle")
        title.setContentsMargins(8, 0, 0, 4)
        layout.addWidget(title)
        for category, (color, glyph) in icons.CATEGORY_STYLE.items():
            item = NavItem(f"cat:{category}", category_label(category), glyph, tile_color=color)
            layout.addWidget(self._add_item(item))

        layout.addStretch(1)
        separator = QFrame()
        separator.setObjectName("Separator")
        layout.addWidget(separator)
        layout.addSpacing(6)
        layout.addWidget(self._add_item(NavItem("settings", _nav_label("settings"), "settings", show_count=False)))

        self._items["all"].setChecked(True)
        self._group.buttonClicked.connect(lambda button: self.selected.emit(button.key))  # type: ignore[attr-defined]

    def _build_brand(self) -> QWidget:
        brand = QWidget()
        row = QHBoxLayout(brand)
        row.setContentsMargins(8, 0, 0, 0)
        row.setSpacing(10)
        logo = QLabel()
        logo.setPixmap(icons.logo_pixmap(34, self.devicePixelRatioF()))
        logo.setFixedSize(34, 34)
        name = QLabel(f"<b>NOVA</b> <span style='color:{current_palette().accent_2}'><b>DM</b></span>")
        name.setStyleSheet("font-size: 20px;")
        name.setAccessibleName(APP_NAME)
        row.addWidget(logo)
        row.addWidget(name)
        row.addStretch(1)
        return brand

    def _add_item(self, item: NavItem) -> NavItem:
        self._items[item.key] = item
        self._group.addButton(item)
        return item

    def select(self, key: str) -> None:
        item = self._items.get(key)
        if item is not None:
            item.setChecked(True)
            self.selected.emit(key)

    def current_key(self) -> str:
        checked = self._group.checkedButton()
        return checked.key if isinstance(checked, NavItem) else "all"  # type: ignore[attr-defined]

    def set_counts(self, counts: dict[str, int]) -> None:
        for key, item in self._items.items():
            if key in counts:
                item.set_count(counts[key])

    def refresh_theme(self) -> None:
        for item in self._items.values():
            item.update()
