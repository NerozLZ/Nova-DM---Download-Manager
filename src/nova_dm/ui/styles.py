"""Paletas (escuro/claro) e folha de estilo Qt."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication


@dataclass(frozen=True, slots=True)
class Palette:
    name: str
    bg: str
    sidebar: str
    panel: str
    card: str
    card_hover: str
    card_selected: str
    border: str
    text: str
    text_muted: str
    text_faint: str
    accent: str
    accent_2: str
    on_accent: str
    success: str
    warning: str
    danger: str
    track: str
    input_bg: str
    badge: str

    def color(self, field_name: str) -> QColor:
        return QColor(getattr(self, field_name))


DARK = Palette(
    name="dark",
    bg="#0b0d14",
    sidebar="#0b0d14",
    panel="#10121a",
    card="#141722",
    card_hover="#171a27",
    card_selected="#1a1e2e",
    border="#1f2332",
    text="#e8eaf2",
    text_muted="#8d93a8",
    text_faint="#5d6279",
    accent="#7c5cff",
    accent_2="#9d6bff",
    on_accent="#ffffff",
    success="#34d27b",
    warning="#f5a524",
    danger="#f0506e",
    track="#232738",
    input_bg="#121520",
    badge="#1c2030",
)

LIGHT = Palette(
    name="light",
    bg="#f2f3f8",
    sidebar="#ffffff",
    panel="#ffffff",
    card="#f7f8fc",
    card_hover="#f0f1f8",
    card_selected="#e9e7ff",
    border="#e2e4ee",
    text="#1a1d29",
    text_muted="#667088",
    text_faint="#98a0b5",
    accent="#6a4cf5",
    accent_2="#8a5cf6",
    on_accent="#ffffff",
    success="#12a85c",
    warning="#d98a06",
    danger="#d9304f",
    track="#e3e5f0",
    input_bg="#ffffff",
    badge="#eceef6",
)

PALETTES = {"dark": DARK, "light": LIGHT}
_current = DARK


def current_palette() -> Palette:
    return _current


def build_stylesheet(p: Palette) -> str:
    return f"""
* {{ outline: 0; }}
QMainWindow, QDialog, QWidget#Root {{ background: {p.bg}; color: {p.text}; }}
QWidget {{ color: {p.text}; font-size: 13px; }}
QLabel {{ background: transparent; }}
QLabel#Muted {{ color: {p.text_muted}; }}
QLabel#Title {{ font-size: 20px; font-weight: 700; }}
QLabel#SectionTitle {{ font-size: 13px; font-weight: 700; color: {p.text_muted}; }}
QWidget#Sidebar {{ background: {p.sidebar}; border-right: 1px solid {p.border}; }}
QFrame#Panel {{ background: {p.panel}; border: 1px solid {p.border}; border-radius: 16px; }}
QFrame#Separator {{ background: {p.border}; max-height: 1px; min-height: 1px; border: none; }}

QLineEdit, QPlainTextEdit, QSpinBox, QComboBox {{
    background: {p.input_bg}; border: 1px solid {p.border}; border-radius: 10px;
    padding: 7px 10px; selection-background-color: {p.accent}; selection-color: {p.on_accent};
}}
QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QComboBox:focus {{ border: 1px solid {p.accent}; }}
QLineEdit#Search {{ padding: 10px 14px 10px 38px; border-radius: 14px; font-size: 14px; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{
    background: {p.panel}; border: 1px solid {p.border}; selection-background-color: {p.card_selected};
    selection-color: {p.text}; padding: 4px; outline: 0;
}}
QSpinBox::up-button, QSpinBox::down-button {{ width: 18px; border: none; background: transparent; }}

QPushButton {{
    background: {p.card}; border: 1px solid {p.border}; border-radius: 10px; padding: 8px 16px;
}}
QPushButton:hover {{ background: {p.card_hover}; }}
QPushButton:pressed {{ background: {p.accent}; border: 1px solid {p.accent}; color: {p.on_accent}; }}
QPushButton:disabled {{ color: {p.text_faint}; }}
QPushButton#Primary {{
    border: none; color: {p.on_accent}; font-weight: 600;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {p.accent}, stop:1 {p.accent_2});
}}
QPushButton#Primary:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {p.accent_2}, stop:1 {p.accent});
}}
QPushButton#Primary:pressed {{ background: {p.card_selected}; border: 1px solid {p.accent}; color: {p.accent_2}; }}
QPushButton#Primary:disabled {{ background: {p.track}; color: {p.text_faint}; }}
QPushButton#Icon {{ padding: 0; border-radius: 12px; min-width: 40px; max-width: 40px; min-height: 40px; max-height: 40px; }}
QPushButton#Danger {{ color: {p.danger}; }}

QCheckBox {{ spacing: 8px; background: transparent; }}
QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 5px; border: 1px solid {p.text_faint}; background: {p.input_bg}; }}
QCheckBox::indicator:checked {{ background: {p.accent}; border: 1px solid {p.accent}; }}

QListView {{ background: transparent; border: none; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollArea > QWidget#qt_scrollarea_viewport, QWidget#SettingsContent {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {p.track}; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {p.text_faint}; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ background: none; height: 0; width: 0; }}

QMenu {{ background: {p.panel}; border: 1px solid {p.border}; border-radius: 10px; padding: 6px; }}
QMenu::item {{ padding: 7px 22px 7px 12px; border-radius: 6px; }}
QMenu::item:selected {{ background: {p.card_selected}; }}
QMenu::item:disabled {{ color: {p.text_faint}; }}
QMenu::separator {{ height: 1px; background: {p.border}; margin: 5px 8px; }}
QToolTip {{ background: {p.panel}; color: {p.text}; border: 1px solid {p.border}; padding: 5px; }}
QStatusBar {{ background: transparent; color: {p.text_muted}; }}
QStatusBar::item {{ border: none; }}
QMessageBox {{ background: {p.bg}; }}
"""


def apply_theme(app: QApplication, name: str) -> Palette:
    global _current  # noqa: PLW0603 - estado de tema partilhado pelos delegates
    _current = PALETTES.get(name, DARK)
    app.setStyle("Fusion")
    app.setStyleSheet(build_stylesheet(_current))
    return _current
