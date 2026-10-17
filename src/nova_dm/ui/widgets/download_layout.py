"""Geometria das colunas, partilhada pelo cabeçalho e pelo delegate dos cartões."""

from __future__ import annotations

from dataclasses import dataclass

CARD_HEIGHT = 72
CARD_MARGIN_X = 6
CARD_MARGIN_Y = 4
ICON_SIZE = 40
BUTTON_SIZE = 32
BUTTON_GAP = 6
CHECK_SIZE = 18
CHECK_X = 14

_GAP = 8
_NAME_MIN = 150
# Colunas opcionais: (nome, largura). Quando falta espaço saem pela ordem inversa desta lista.
_OPTIONAL = (("size", 72), ("type", 78), ("progress", 104), ("status", 92), ("speed", 82), ("eta", 96))
_DROP_ORDER = ("eta", "speed", "type", "size", "status")


@dataclass(frozen=True, slots=True)
class Columns:
    """Posições x e larguras (relativas ao início do cartão). Largura 0 = coluna oculta."""

    name_x: int
    name_w: int
    size_x: int
    size_w: int
    type_x: int
    type_w: int
    progress_x: int
    progress_w: int
    status_x: int
    status_w: int
    speed_x: int
    speed_w: int
    eta_x: int
    eta_w: int
    actions_x: int


def compute_columns(card_width: int) -> Columns:
    actions_w = BUTTON_SIZE * 2 + BUTTON_GAP
    actions_x = card_width - actions_w - 12
    name_x = CHECK_X + CHECK_SIZE + 12 + ICON_SIZE + 12
    visible = {name: width for name, width in _OPTIONAL}

    def fixed() -> int:
        return sum(w + _GAP for w in visible.values())

    for dropped in _DROP_ORDER:
        if actions_x - _GAP - fixed() - name_x >= _NAME_MIN:
            break
        visible.pop(dropped, None)
    if "progress" in visible and actions_x - _GAP - fixed() - name_x < _NAME_MIN:
        visible["progress"] = 90

    cursor = actions_x - _GAP
    positions: dict[str, tuple[int, int]] = {}
    for name, _ in reversed(_OPTIONAL):
        width = visible.get(name, 0)
        if width:
            cursor -= width
            positions[name] = (cursor, width)
            cursor -= _GAP
        else:
            positions[name] = (cursor, 0)
    name_w = max(80, cursor + _GAP - name_x - _GAP)

    def at(name: str) -> tuple[int, int]:
        return positions[name]

    return Columns(
        name_x, name_w,
        *at("size"), *at("type"), *at("progress"), *at("status"), *at("speed"), *at("eta"),
        actions_x,
    )
