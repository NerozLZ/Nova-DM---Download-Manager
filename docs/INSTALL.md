# Instalação

## A partir do código-fonte
1. Instalar `aria2` pelo gestor de pacotes da distribuição (ou indicar o executável em Definições › Motor de downloads).
2. `python -m venv .venv && . .venv/bin/activate && pip install -e .`
3. `nova-dm`

## Flatpak (Bazzite)
Ver `FLATPAK.md`. O manifesto ainda não foi construído nem testado.

Dados: `~/.local/share/nova-dm` (base de dados), `~/.config/nova-dm` e `~/.local/state/nova-dm` (logs), seguindo o XDG (dentro do Flatpak, em `~/.var/app/io.github.NerozLZ.NovaDM`).
