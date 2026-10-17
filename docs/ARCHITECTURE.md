# Arquitetura

Camadas (as dependências apontam para baixo):

- `ui/` — janelas, páginas, diálogos e widgets (sem lógica de downloads).
- `services/` — `DownloadController` (QObject; corre o trabalho num `QThread`, sondagem de 500 ms, sinais para a UI), `DownloadService`, `MetadataService`.
- `core/` — `DownloadEngine` (interface abstrata), `Aria2Engine`, `Aria2Process`, cliente JSON-RPC, `DownloadManager` (fila e regras), modelos.
- `database/` — `Repository` SQLite.
- `utils/`, `config.py`, `i18n.py`, `errors.py`.

A GUI nunca bloqueia: todo o I/O de rede/RPC/base de dados passa pelo controlador. Trocar de motor exige apenas outra implementação de `DownloadEngine`.

Segurança: URLs e caminhos validados (`utils/urls.py`, `utils/files.py`), sem sobrescrita acidental, sem path traversal, credenciais removidas dos logs (`utils/logging_setup.py`), sem telemetria, ficheiros descarregados nunca são executados.

Extensão de browser: `browser-extension/firefox/` (MV2, `downloads.onCreated`). O recetor (`services/browser_bridge.py`) é HTTP só em 127.0.0.1, com token: `POST /v1/links` com `{"urls": [...], "referer", "user_agent", "cookies", "filename"}` (cabeçalho `Authorization: Bearer <token>`). O contexto (`RequestContext`) vive só em memória e é passado ao aria2 como `referer`, `user-agent` e `header`; nunca é gravado nem registado. Com «perguntar antes de adicionar» abre o diálogo; sem isso entra direto na pasta predefinida. Emparelhamento: `POST /v1/pair` (sem token, só com Origin de extensão e Host local) pede confirmação ao utilizador na janela do Nova DM e só então devolve o token; um pedido de cada vez, com intervalo mínimo e limite de 60 s. Pendente: Chrome/Edge, assinatura Mozilla.
