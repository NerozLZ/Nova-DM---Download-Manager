"""Ponto de entrada: `nova-dm` ou `python -m nova_dm.main`."""

from __future__ import annotations

import sys

from nova_dm.app import NovaDMApp, configure_high_dpi


def main() -> int:
    configure_high_dpi()
    return NovaDMApp().run()


if __name__ == "__main__":
    sys.exit(main())
