"""Exceções do domínio da aplicação."""

from __future__ import annotations


class NovaDMError(Exception):
    """Erro base; a mensagem pode ser mostrada ao utilizador."""


class InvalidUrlError(NovaDMError):
    """O URL não é um URL HTTP/HTTPS válido."""


class InvalidDestinationError(NovaDMError):
    """A pasta ou o nome de ficheiro de destino não são válidos ou seguros."""


class InsufficientSpaceError(NovaDMError):
    """Não existe espaço livre suficiente no destino."""


class EngineError(NovaDMError):
    """Falha ao comunicar com o motor de downloads."""


class EngineUnavailableError(EngineError):
    """O motor de downloads não está disponível (não instalado ou não arrancou)."""


class RpcError(EngineError):
    """Erro devolvido pelo servidor JSON-RPC do aria2."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(f"aria2 RPC error {code}: {message}")
        self.code = code
        self.rpc_message = message


class ProbeError(NovaDMError):
    """Não foi possível obter os metadados de um URL."""
