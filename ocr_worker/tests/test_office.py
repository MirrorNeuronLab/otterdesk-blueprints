"""Office conversion is bounded, cancellable and never invokes a shell."""

import importlib.util
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

SOURCE = Path(__file__).resolve().parents[1] / "payloads/domain/office.py"


@pytest.fixture
def office():
    spec = importlib.util.spec_from_file_location("ocr_office_under_test", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def process(office, monkeypatch, tmp_path):
    source = tmp_path / "source with spaces;$(ignored).docx"
    source.write_bytes(b"synthetic Office source")
    state = SimpleNamespace(
        code=0, pdf=b"%PDF-fixture", waits=0, polls=0, killed=[], profile=""
    )

    def start(command, **options):
        state.command, state.options = command, options
        profile = Path(command[1].split("file://", 1)[1])
        from urllib.parse import unquote

        state.profile = (
            Path(unquote(str(profile))) / "user/registrymodifications.xcu"
        ).read_text()
        if state.pdf is not None:
            (Path(command[-2]) / (source.stem + ".pdf")).write_bytes(state.pdf)

        def wait(timeout=None):
            state.waits += 1
            if state.code is None and timeout:
                raise subprocess.TimeoutExpired(command, timeout)
            return state.code

        return SimpleNamespace(pid=123, wait=wait, poll=lambda: state.code)

    monkeypatch.setattr(office.subprocess, "Popen", start)
    monkeypatch.setattr(
        office.os, "killpg", lambda pid, signal: state.killed.append(pid)
    )
    state.source = source
    return state


def test_isolated_profile_disables_macros_and_link_updates(office, process):
    assert (
        office.render_office(process.source, check=lambda: None, max_bytes=100)
        == b"%PDF-fixture"
    )
    assert process.command[0] == "libreoffice"
    assert process.command[-1] == str(process.source)
    assert process.options["start_new_session"] is True
    assert "shell" not in process.options
    assert "DisableMacrosExecution" in process.profile
    assert "DisableActiveContent" in process.profile
    assert "/org.openoffice.Office.Calc/Content/Update" in process.profile
    assert "/org.openoffice.Office.Writer/Content/Update" in process.profile
    assert not process.killed


@pytest.mark.parametrize(
    "data,code",
    [(None, 0), (b"not a PDF", 0), (b"%PDF-" + b"x" * 100, 0), (b"%PDF-x", 1)],
)
def test_invalid_missing_oversized_or_failed_conversion(office, process, data, code):
    process.pdf, process.code = data, code
    with pytest.raises(office.DocumentInputError):
        office.render_office(process.source, check=lambda: None, max_bytes=100)


def test_cancellation_stops_converter_process_group(office, process):
    process.code = None
    checks = 0

    def cancel():
        nonlocal checks
        checks += 1
        if checks == 3:
            raise RuntimeError("cancelled")

    with pytest.raises(RuntimeError, match="cancelled"):
        office.render_office(process.source, check=cancel, max_bytes=100)
    assert process.killed == [123]


def test_deadline_stops_converter_process_group(office, process, monkeypatch):
    process.code = None
    clock = iter([0, 181])
    monkeypatch.setattr(office.time, "monotonic", lambda: next(clock))
    with pytest.raises(office.DocumentInputError, match="deadline"):
        office.render_office(process.source, check=lambda: None, max_bytes=100)
    assert process.killed == [123]


def test_missing_converter_is_a_worker_failure(office, tmp_path, monkeypatch):
    def missing(*args, **kwargs):
        raise FileNotFoundError("missing")

    monkeypatch.setattr(office.subprocess, "Popen", missing)
    with pytest.raises(RuntimeError, match="requires LibreOffice"):
        office.render_office(
            tmp_path / "source.docx", check=lambda: None, max_bytes=100
        )
