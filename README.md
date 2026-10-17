# Nova DM — Nova Download Manager

Gestor de downloads para Linux (Python 3.12+, PySide6, aria2 via JSON-RPC, SQLite). Licença: freeware (ver `LICENSE`).

## Estado (Fase 1)

Implementado e testado: adicionar downloads (vários links, nome e pasta, ligações por download; links também por arrastar e largar), pausa/retoma/cancelar/repetir,
fila com limite de downloads simultâneos e ordem escolhida (arrastar, menu, Alt+↑/↓), ordenação por coluna (clicar no título: crescente, decrescente, ordem manual), seleção múltipla com caixas e «selecionar tudo», remover só da lista ou com os ficheiros, categorias automáticas, histórico em SQLite, retoma ao arrancar, limite global de
velocidade, tema escuro/claro, 35 idiomas, abrir ficheiro/pasta (com aviso para executáveis — nunca se executa nada
automaticamente).


## Integração com o Firefox

A extensão está em `browser-extension/firefox/` (Manifest V2). Quando um download começa no Firefox, envia o link
(com referer, user-agent e cookies, para sites com sessão iniciada) ao Nova DM e cancela o download do Firefox
**só depois** de o Nova DM o aceitar; se o Nova DM estiver fechado, o Firefox descarrega normalmente.

1. Nova DM › Definições › Integração com o navegador: ligar, copiar o token, guardar.
2. Firefox: `about:debugging#/runtime/this-firefox` › «Carregar extensão temporária…» › escolher `manifest.json`
   (temporária até reiniciar o Firefox; a instalação permanente exige assinatura da Mozilla — pendente).
3. Opções da extensão: «Ligar ao Nova DM» e confirmar o pedido na janela do Nova DM (o token passa sozinho; só é preciso copiá-lo à mão numa configuração manual). O botão da barra liga/desliga a captura.

Se o Nova DM estiver fechado, a extensão abre-o sozinha (endereço `novadm://`, registado pelo `.desktop`; o Firefox pede confirmação na primeira vez) e só depois lhe entrega o download. Isto pode ser desligado nas opções da extensão. O Nova DM passou a ter uma única instância: abrir de novo só traz a janela existente para a frente.

Os cookies só existem em memória: se fechar o Nova DM a meio, ao retomar essa transferência pode ser preciso
voltar a iniciá-la no browser. **Não testado num Firefox real** (só o recetor e o motor têm testes automáticos).


# Nova DM — Nova Download Manager

Download manager for Linux (Python 3.12+, PySide6, aria2 via JSON-RPC, SQLite). License: freeware (see LICENSE).

Status (Phase 1)

Implemented and tested: add downloads (multiple links, name and folder, links per download; links also by drag and drop), pause/resume/cancel/repeat, queue with limit of simultaneous downloads and chosen order (drag, menu, Alt+↑/↓), sorting by column (click on the title: ascending, descending, manual order), multiple selection with boxes and "select all", remove only from the list or with the files, automatic categories, history in SQLite, resumes on startup, global speed limit, dark/light theme, 35 languages, open file/folder (with warning for executables — you never run anything automatically).
Firefox Integration

The extension is located in browser-extension/firefox/ (Manifest V2). When a download starts in Firefox, it sends the link (with referrer, user-agent, and cookies, for logged-in sites) to Nova DM and cancels the Firefox download only after Nova DM accepts it; if Nova DM is closed, Firefox downloads normally.

Nova DM › Settings › Browser Integration: connect, copy token, save.

Firefox: about:debugging#/runtime/this-firefox › «Load temporary extension…» › choose manifest.json (temporary until Firefox restarts; permanent installation requires Mozilla subscription — pending).

Extension options: «Connect to Nova DM» and confirm the request in the Nova DM window (the token passes automatically; you only need to copy it manually in a manual setup). The button on the toolbar turns capture on/off.

If Nova DM is closed, the extension opens it automatically (address novadm://, registered by .desktop; Firefox asks for confirmation the first time) and only then delivers the download to you. This can be disabled in the extension options. Nova DM now has a single instance: reopening it only brings the existing window to the forefront.

Cookies only exist in memory: if you close Nova DM mid-process, resuming the download may require restarting it in the browser. Not tested on a real Firefox (only the receiver and the mechanism have automatic tests).
