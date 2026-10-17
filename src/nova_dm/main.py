"""Ponto de entrada: `nova-dm` ou `python -m nova_dm.main`."""

from __future__ import annotations

import sys

from nova_dm.app import NovaDMApp, configure_high_dpi
from nova_dm.utils.single_instance import SingleInstance


def main() -> int:
    configure_high_dpi()
    guard = SingleInstance()
    if not guard.acquire():
        return 0  # já está aberto: a outra instância foi avisada
    try:
        app = NovaDMApp()
        guard.listen(app.window.bring_to_front)
        return app.run()
    finally:
        guard.release()


if __name__ == "__main__":
    sys.exit(main())
