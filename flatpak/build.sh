#!/usr/bin/env bash
# Constrói e instala o Nova DM como Flatpak (utilizador). Executar a partir de qualquer pasta.
set -euo pipefail
cd "$(dirname "$0")"

flatpak remote-add --if-not-exists --user flathub https://dl.flathub.org/repo/flathub.flatpakrepo
flatpak install --user -y flathub org.kde.Platform//6.11 org.kde.Sdk//6.11 io.qt.PySide.BaseApp//6.11

# flatpak-builder: no Bazzite instala-se como Flatpak (ou usa o que já tiveres)
if command -v flatpak-builder >/dev/null; then
  BUILDER=(flatpak-builder)
else
  flatpak install --user -y flathub org.flatpak.Builder
  BUILDER=(flatpak run org.flatpak.Builder)
fi

"${BUILDER[@]}" --user --install --force-clean --install-deps-from=flathub \
  --state-dir=../.flatpak-builder ../build-dir io.github.NerozLZ.NovaDM.yaml

echo "Pronto. Executar com: flatpak run io.github.NerozLZ.NovaDM"
