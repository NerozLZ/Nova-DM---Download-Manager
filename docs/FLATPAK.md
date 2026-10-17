# Flatpak

`flatpak/io.github.NerozLZ.NovaDM.yaml` compila o aria2 1.37.0 (sha256 verificado a partir do tarball oficial) e instala o Nova DM.

**Não foi construído nem testado**: o `flatpak-builder` não existia no ambiente de desenvolvimento. Antes de usar, confirmar:
- (runtime KDE 6.11 e PySide BaseApp 6.11 já confirmados no Flathub; se saírem versões novas, atualizar os dois campos);
- que o `pip install` offline funciona (pode ser preciso gerar dependências com `flatpak-pip-generator`);
- se o `--stop-with-process` e o acesso a `127.0.0.1` funcionam dentro da sandbox.

Permissões: rede, `xdg-download`, Wayland/X11. Outras pastas via portal de ficheiros.
Licença: o aria2 é GPL-2.0-or-later; ao distribuir o Flatpak é preciso disponibilizar o código-fonte do aria2 (ver `THIRD_PARTY.md`).
BitTorrent/Metalink estão desativados na compilação para reduzir dependências.

## Construir
`./flatpak/build.sh` (instala runtimes, flatpak-builder e a app para o utilizador). Executar: `flatpak run io.github.NerozLZ.NovaDM`.
