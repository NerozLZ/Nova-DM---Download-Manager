# Nova DM — Nova Download Manager

Gestor de downloads para Linux (Python 3.12+, PySide6, aria2 via JSON-RPC, SQLite). Licença: freeware (ver `LICENSE`).

## Estado (Fase 1)

Implementado e testado: adicionar downloads (vários links, nome e pasta, ligações por download; links também por arrastar e largar), pausa/retoma/cancelar/repetir,
fila com limite de downloads simultâneos e ordem escolhida (arrastar, menu, Alt+↑/↓), ordenação por coluna (clicar no título: crescente, decrescente, ordem manual), seleção múltipla com caixas e «selecionar tudo», remover só da lista ou com os ficheiros, categorias automáticas, histórico em SQLite, retoma ao arrancar, limite global de
velocidade, tema escuro/claro, 35 idiomas, abrir ficheiro/pasta (com aviso para executáveis — nunca se executa nada
automaticamente).

**Pendente (Fase 2/3, não implementado):** agendamento, categorias configuráveis,
bandeja do sistema/comportamento ao fechar,
limite de velocidade por download, BitTorrent/Metalink (desativados no Flatpak).

## Executar

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
nova-dm            # requer o aria2c instalado (ou configurado nas Definições)
pytest             # QT_QPA_PLATFORM=offscreen em sistemas sem ecrã
```

Mais em `docs/`: `INSTALL.md`, `ARCHITECTURE.md`, `DEPENDENCIES.md`, `FLATPAK.md`, `TRANSLATIONS.md`.

## Integração com o Firefox

A extensão está em `browser-extension/firefox/` (Manifest V2). Quando um download começa no Firefox, envia o link
(com referer, user-agent e cookies, para sites com sessão iniciada) ao Nova DM e cancela o download do Firefox
**só depois** de o Nova DM o aceitar; se o Nova DM estiver fechado, o Firefox descarrega normalmente.

1. Nova DM › Definições › Integração com o navegador: ligar, copiar o token, guardar.
2. Firefox: `about:debugging#/runtime/this-firefox` › «Carregar extensão temporária…» › escolher `manifest.json`
   (temporária até reiniciar o Firefox; a instalação permanente exige assinatura da Mozilla — pendente).
3. Opções da extensão: «Ligar ao Nova DM» e confirmar o pedido na janela do Nova DM (o token passa sozinho; só é preciso copiá-lo à mão numa configuração manual). O botão da barra liga/desliga a captura.

Os cookies só existem em memória: se fechar o Nova DM a meio, ao retomar essa transferência pode ser preciso
voltar a iniciá-la no browser. **Não testado num Firefox real** (só o recetor e o motor têm testes automáticos).
