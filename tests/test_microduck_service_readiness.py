"""The live UI can warm before serving and needs no connected browser."""

import importlib
from pathlib import Path
from types import SimpleNamespace


def test_registrar_waits_for_page_readiness_and_then_checks_live_health(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "microduck_controller/payloads"))
    service = importlib.import_module("domain.web_ui_service")
    block = SimpleNamespace(resources={"worker": SimpleNamespace(is_alive=lambda: True),
                                      "endpoint": {"url": "http://private-worker:1234"}})
    healthy = False
    monkeypatch.setattr(service, "upstream_healthy", lambda _: healthy)
    monkeypatch.setattr(service, "probe_web_ui", lambda _: {"ready": True})
    assert service.health(block, {}) is True
    assert service.ready(block, {}) is False
    healthy = True
    assert service.ready(block, {}) is True
    healthy = False
    assert service.health(block, {}) is False
