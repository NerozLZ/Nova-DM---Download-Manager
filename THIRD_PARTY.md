# Componentes de terceiros

| Componente | Utilização | Licença |
|---|---|---|
| [aria2](https://aria2.github.io/) | Motor de downloads, executado como processo separado e controlado por JSON-RPC | GPL-2.0-or-later |
| [Qt for Python (PySide6)](https://doc.qt.io/qtforpython-6/) | Interface gráfica | LGPL-3.0 / GPL / comercial |
| [pytest](https://pytest.org/), [pytest-qt](https://pytest-qt.readthedocs.io/) | Apenas testes (não distribuídos) | MIT |

O aria2 não é incorporado no código do Nova DM: é invocado como programa independente. Quem distribuir
o Nova DM juntamente com um binário do aria2 (por exemplo num Flatpak) deve cumprir as obrigações da GPL
para esse binário, incluindo disponibilizar o código-fonte correspondente.

Os ícones da interface são desenhados no próprio projeto (`src/nova_dm/ui/icons.py`).
