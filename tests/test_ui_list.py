"""Interação da lista: ordem, seleção, remoção com escolha e links largados (Qt offscreen)."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt, QUrl, Signal, QObject  # noqa: E402
from PySide6.QtGui import QDropEvent  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from nova_dm.config import Settings  # noqa: E402
from nova_dm.core.models import DownloadRecord, DownloadStatus  # noqa: E402
from nova_dm.database.repository import Repository  # noqa: E402
from nova_dm.ui.main_window import MainWindow  # noqa: E402
from nova_dm.ui.widgets.download_list import IDS_MIME, check_rect, dropped_links  # noqa: E402


class FakeController(QObject):
    records_changed = Signal(list)
    error = Signal(str)
    engine_ready = Signal()
    engine_failed = Signal(str)
    add_finished = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple] = []

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        return lambda *args, **kwargs: self.calls.append((name, *args))


def make_records(n: int = 4) -> list[DownloadRecord]:
    return [
        DownloadRecord(url=f"http://h/{i}", filename=f"f{i}.bin", directory="/tmp", id=i, position=i,
                       status=DownloadStatus.ACTIVE if i % 2 else DownloadStatus.COMPLETED, total_bytes=100)
        for i in range(1, n + 1)
    ]


@pytest.fixture
def window(qtbot):
    repo = Repository(":memory:")
    controller = FakeController()
    win = MainWindow(Settings(), repo, controller)
    win.resize(1320, 780)
    win._closing_confirmed = True  # não perguntar ao fechar (modal) no fim do teste
    qtbot.addWidget(win)
    win.show()
    controller.records_changed.emit(make_records())
    win.controller = controller
    yield win
    repo.close()


def names(win) -> list[str]:
    return [win.page.proxy.index(r, 0).data().__str__() for r in range(win.page.proxy.rowCount())]


def test_rows_follow_position_and_keep_selection_when_reordered(window) -> None:
    view = window.page.view
    assert names(window) == ["f1.bin", "f2.bin", "f3.bin", "f4.bin"]
    view.selectionModel().select(window.page.proxy.index(1, 0), view.selectionModel().SelectionFlag.Select)
    records = make_records()
    records[0].position, records[1].position = 2, 1  # f2 passa para o topo
    window.controller.records_changed.emit(records)
    assert names(window)[:2] == ["f2.bin", "f1.bin"]
    assert window.page.selected_ids() == [2]


def test_checkbox_toggles_rows_and_header_selects_all(window, qtbot) -> None:
    view = window.page.view
    for row in (0, 2):
        index = window.page.proxy.index(row, 0)
        card = window.page.delegate.card_rect(view.visualRect(index))
        QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=check_rect(card).center())
    assert sorted(window.page.selected_ids()) == [1, 3]
    assert window.page.header.check_state is Qt.CheckState.PartiallyChecked
    assert window.delete_button.isEnabled()
    window.page.toggle_select_all()
    assert sorted(window.page.selected_ids()) == [1, 2, 3, 4]
    assert window.page.header.check_state is Qt.CheckState.Checked
    window.page.toggle_select_all()
    assert window.page.selected_ids() == []
    assert not window.delete_button.isEnabled()


def test_remove_asks_list_only_or_with_files(window) -> None:
    window.page.view.selectAll()
    for answer, expected in (("list", "remove"), ("files", "delete_files")):
        window.controller.calls.clear()
        window.choose_removal = lambda records, a=answer: a
        window._remove(window.page.selected_ids())
        assert window.controller.calls == [(expected, [1, 2, 3, 4])]
    window.controller.calls.clear()
    window.choose_removal = lambda records: None
    window._remove(window.page.selected_ids())
    assert window.controller.calls == []


def test_context_actions_call_controller(window) -> None:
    window._move([2, 3], "up")
    assert window.controller.calls == [("move", [2, 3], "up")]


def _drop(widget, mime: QMimeData, pos: QPoint) -> None:
    event = QDropEvent(QPointF(pos), Qt.DropAction.MoveAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    widget.dropEvent(event)


def test_drag_reorder_emits_target(window, qtbot) -> None:
    view = window.page.view
    mime = QMimeData()
    mime.setData(IDS_MIME, b"4")
    rect = view.visualRect(window.page.proxy.index(0, 0))
    with qtbot.waitSignal(view.rows_moved) as blocker:
        _drop(view, mime, QPoint(rect.center().x(), rect.top() + 3))
    assert blocker.args == [[4], 1, False]  # antes da primeira linha (id 1)
    below = view.visualRect(window.page.proxy.index(1, 0))
    with qtbot.waitSignal(view.rows_moved) as blocker:
        _drop(view, mime, QPoint(below.center().x(), below.bottom() - 3))
    assert blocker.args == [[4], 2, True]
    with qtbot.waitSignal(view.rows_moved) as blocker:
        _drop(view, mime, QPoint(10, view.viewport().height() - 2))  # área vazia = fim
    assert blocker.args[1] is None


def test_dropped_links_open_add_dialog(window, monkeypatch) -> None:
    opened: list[str] = []
    monkeypatch.setattr(window, "add_download", lambda text="": opened.append(text))
    mime = QMimeData()
    mime.setUrls([QUrl("https://example.org/a.zip"), QUrl("file:///etc/passwd")])
    mime.setText("https://example.org/b.iso\nnada")
    assert dropped_links(mime) == ["https://example.org/a.zip", "https://example.org/b.iso"]
    _drop(window.page.view, mime, QPoint(20, 20))
    assert opened == ["https://example.org/a.zip\nhttps://example.org/b.iso"]


def test_non_link_drop_is_ignored() -> None:
    mime = QMimeData()
    mime.setText("só texto")
    assert dropped_links(mime) == []


# --- ordenar por coluna ------------------------------------------------------------------------

def _varied() -> list[DownloadRecord]:
    return [
        DownloadRecord(url="http://h/1", filename="banana.zip", directory="/t", id=1, position=1, total_bytes=500,
                       status=DownloadStatus.PAUSED, category="archive"),
        DownloadRecord(url="http://h/2", filename="Cereja.mp4", directory="/t", id=2, position=2, total_bytes=0,
                       status=DownloadStatus.ACTIVE, download_speed=900, category="video"),
        DownloadRecord(url="http://h/3", filename="abacate.iso", directory="/t", id=3, position=3, total_bytes=100,
                       status=DownloadStatus.COMPLETED, category="archive"),
    ]


def shown(win) -> list[int]:
    return [win.page.proxy.index(r, 0).data(Qt.ItemDataRole.UserRole + 1).id for r in range(win.page.proxy.rowCount())]


@pytest.mark.parametrize(
    ("column", "ascending", "expected"),
    [
        ("name", True, [3, 1, 2]),  # abacate, banana, Cereja (sem distinguir maiúsculas)
        ("name", False, [2, 1, 3]),
        ("size", True, [2, 3, 1]),  # tamanho desconhecido (0) vem primeiro
        ("type", True, [3, 2, 1]),  # iso < mp4 < zip
        ("status", True, [2, 1, 3]),  # em curso, em pausa, concluído
        ("speed", False, [2, 1, 3]),
        ("progress", False, [3, 2, 1]),  # 100 %, depois empate a 0 % (desempate pelo nome, invertido)
    ],
)
def test_sorting(window, column, ascending, expected) -> None:
    window.controller.records_changed.emit(_varied())
    window.page.proxy.set_sort(column, ascending)
    assert shown(window) == expected


def test_header_click_cycles_ascending_descending_manual(window) -> None:
    window.controller.records_changed.emit(_varied())
    page = window.page
    rect = page.header._column_rects()["name"]
    states = []
    for _ in range(3):
        QTest.mouseClick(page.header, Qt.MouseButton.LeftButton, pos=rect.center())
        states.append((page.proxy.sort_column, page.proxy.sort_ascending, shown(window)))
    assert states[0] == ("name", True, [3, 1, 2])
    assert states[1] == ("name", False, [2, 1, 3])
    assert states[2] == (None, True, [1, 2, 3])  # volta à ordem manual
    assert page.view.reorder_enabled


def test_manual_reorder_is_blocked_while_sorted(window) -> None:
    window.page.cycle_sort("name")
    assert not window.page.view.reorder_enabled
    window.controller.calls.clear()
    window._move([1], "up")
    window._on_rows_moved([1], 2, False)
    assert window.controller.calls == []
    assert "sorted" in window.statusBar().currentMessage().lower() or window.statusBar().currentMessage()


def test_selection_survives_sorting(window) -> None:
    window.controller.records_changed.emit(_varied())
    window.page.view.selectionModel().select(window.page.proxy.index(0, 0), window.page.view.selectionModel().SelectionFlag.Select)
    before = window.page.selected_ids()
    window.page.cycle_sort("name")
    assert window.page.selected_ids() == before


def test_license_dialog_shows_texts(window, qtbot) -> None:
    from nova_dm.ui.dialogs.license_dialog import LicenseDialog

    dialog = LicenseDialog(window)
    qtbot.addWidget(dialog)
    tabs = dialog.findChild(__import__("PySide6.QtWidgets", fromlist=["QTabWidget"]).QTabWidget)
    assert tabs.count() == 2
    assert "Freeware" in tabs.widget(0).toPlainText()
    assert "aria2" in tabs.widget(1).toPlainText()
