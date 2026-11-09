"""Shared-shell rendering and inert source data, without network or model calls."""

from html.parser import HTMLParser
import importlib
import json
from pathlib import Path
import sys

from mn_web_report_skill import asset_bytes


def test_report_reuses_the_shared_shell_and_keeps_external_text_inert(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1] / "payloads"))
    for name in list(sys.modules):
        if name == "domain" or name.startswith("domain."):
            monkeypatch.delitem(sys.modules, name)
    render = importlib.import_module("domain.reporting").render
    hostile = '</script><img src=x onerror="alert(1)">'
    record = {
        "source": hostile,
        "source_sha256": "a" * 64,
        "duration_seconds": 1,
        "chunks": [
            {
                "index": 0,
                "start_seconds": 0,
                "end_seconds": 1,
                "audio": "audio/captured.wav",
                "text": hostile,
                "alignment": {
                    "status": "ready",
                    "words": [],
                    "speakers": [],
                    "segments": [],
                },
            }
        ],
    }
    html = render(
        record, [{"source": hostile, "page": "index.html"}], "test-run"
    ).decode()
    assert asset_bytes("report-ui.js").decode() in html
    assert asset_bytes("report-template.css").decode() in html
    assert hostile not in html

    class Shell(HTMLParser):
        def __init__(self):
            super().__init__()
            self.policy = ""
            self.in_data = False
            self.data = ""

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == "meta" and attrs.get("http-equiv") == "Content-Security-Policy":
                self.policy = attrs["content"]
            if tag == "script" and attrs.get("id") == "report-data":
                self.in_data = True

        def handle_endtag(self, tag):
            if tag == "script":
                self.in_data = False

        def handle_data(self, value):
            if self.in_data:
                self.data += value

    shell = Shell()
    shell.feed(html)
    assert json.loads(shell.data)["recording"]["source"] == hostile
    assert "media-src 'self';" in shell.policy
    assert "connect-src 'none'" in shell.policy
    assert "script-src 'sha256-" in shell.policy
    assert "unsafe-inline" not in shell.policy
