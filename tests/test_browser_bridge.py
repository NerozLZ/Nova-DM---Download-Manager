"""Testes do recetor local da extensão e da passagem do contexto HTTP ao aria2."""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request

import pytest

from nova_dm.core.aria2_engine import Aria2Engine
from nova_dm.core.models import AddRequest, RequestContext
from nova_dm.services.browser_bridge import BrowserBridge, parse_context

TOKEN = "t" * 32


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def bridge(qapp):
    b = BrowserBridge()
    port = _free_port()
    b.apply(True, port, TOKEN)
    received: list = []
    b.links_received.connect(lambda urls, ctx: received.append((urls, ctx)))
    yield b, port, received
    b.stop()


def _post(port, body, token=TOKEN, origin="moz-extension://abc"):
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    if origin:
        headers["Origin"] = origin
    req = urllib.request.Request(f"http://127.0.0.1:{port}/v1/links", json.dumps(body).encode(), headers)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status
    except urllib.error.HTTPError as exc:
        return exc.code


def test_accepts_links_with_context(bridge, qapp):
    _b, port, received = bridge
    body = {"urls": ["https://example.com/a.zip"], "referer": "https://example.com/p",
            "user_agent": "UA/1", "cookies": "a=b", "filename": "a.zip"}
    assert _post(port, body) == 200
    qapp.processEvents()
    assert received == [(["https://example.com/a.zip"], {
        "referer": "https://example.com/p", "user_agent": "UA/1", "cookies": "a=b", "filename": "a.zip"})]


def test_rejects_bad_token_and_web_origin(bridge):
    _b, port, received = bridge
    body = {"urls": ["https://example.com/a.zip"]}
    assert _post(port, body, token="x" * 32) == 403
    assert _post(port, body, origin="https://evil.example") == 403
    assert received == []


def test_parse_context_drops_unsafe_values():
    ctx = parse_context({"referer": "javascript:alert(1)", "user_agent": "a\r\nX: y", "cookies": 5, "filename": "ok"})
    assert ctx == {"referer": "", "user_agent": "", "cookies": "", "filename": "ok"}


def test_engine_passes_context_to_aria2(tmp_path):
    calls: list = []

    class FakeClient:
        def add_uri(self, url, options):
            calls.append(options)
            return "gid"

    engine = Aria2Engine()
    engine._client = lambda: FakeClient()  # type: ignore[method-assign]
    ctx = RequestContext("https://example.com/p", "UA/1", "a=b")
    engine.add(AddRequest("https://example.com/a.zip", str(tmp_path), "a.zip", context=ctx))
    assert calls[0]["referer"] == "https://example.com/p"
    assert calls[0]["user-agent"] == "UA/1"
    assert calls[0]["header"] == ["Cookie: a=b"]
    assert "a=b" not in repr(ctx)
