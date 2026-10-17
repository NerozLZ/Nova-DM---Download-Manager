"""Uma só instância do Nova DM.

Necessário para a extensão do navegador poder abrir o Nova DM com segurança: se a aplicação já estiver
aberta, o segundo arranque só pede à primeira que venha para a frente e termina.
"""

from __future__ import annotations

import logging
import os
import tempfile
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QLockFile
from PySide6.QtNetwork import QLocalServer, QLocalSocket

log = logging.getLogger(__name__)

_SERVER_NAME = "io.github.NerozLZ.NovaDM"


def _lock_path() -> Path:
    base = os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()
    return Path(base) / "nova-dm.lock"


class SingleInstance:
    def __init__(self) -> None:
        self._lock = QLockFile(str(_lock_path()))
        self._server: QLocalServer | None = None

    def acquire(self) -> bool:
        """True se esta é a primeira instância. Caso contrário avisa a que já está aberta."""
        if self._lock.tryLock(0):
            return True
        socket = QLocalSocket()
        socket.connectToServer(_SERVER_NAME)
        if socket.waitForConnected(1500):
            socket.write(b"show\n")
            socket.waitForBytesWritten(1500)
            socket.disconnectFromServer()
        else:
            log.warning("Já existe uma instância, mas não respondeu ao pedido para vir para a frente")
        return False

    def listen(self, on_show: Callable[[], None]) -> None:
        """Chamar depois de criar a QApplication."""
        QLocalServer.removeServer(_SERVER_NAME)
        server = QLocalServer()
        server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        if not server.listen(_SERVER_NAME):
            log.warning("Não foi possível escutar pedidos de outras instâncias: %s", server.errorString())
            return

        def handle() -> None:
            while (conn := server.nextPendingConnection()) is not None:
                conn.readyRead.connect(lambda c=conn: (c.readAll(), on_show()))
                conn.disconnected.connect(conn.deleteLater)

        server.newConnection.connect(handle)
        self._server = server

    def release(self) -> None:
        if self._server is not None:
            self._server.close()
        self._lock.unlock()
