"""Render accepted Office sources to PDF inside the OCR worker."""

import os
import signal
import subprocess
import tempfile
import time
from pathlib import Path


class DocumentInputError(ValueError):
    """A source cannot be prepared; safe to report without document contents."""


PROFILE = """<?xml version="1.0" encoding="UTF-8"?>
<oor:items xmlns:oor="http://openoffice.org/2001/registry">
 <item oor:path="/org.openoffice.Office.Common/Security/Scripting">
  <prop oor:name="DisableMacrosExecution" oor:op="fuse"><value>true</value></prop>
  <prop oor:name="DisableActiveContent" oor:op="fuse"><value>true</value></prop>
  <prop oor:name="BlockUntrustedRefererLinks" oor:op="fuse"><value>true</value></prop>
 </item>
 <item oor:path="/org.openoffice.Office.Writer/Content/Update">
  <prop oor:name="Link" oor:op="fuse"><value>2</value></prop>
 </item>
 <item oor:path="/org.openoffice.Office.Calc/Content/Update">
  <prop oor:name="Link" oor:op="fuse"><value>1</value></prop>
 </item>
</oor:items>
"""


def render_office(source: Path, *, check, max_bytes: int) -> bytes:
    check()
    with tempfile.TemporaryDirectory(prefix="ocr-office-") as temporary:
        root = Path(temporary)
        profile = root / "profile"
        (profile / "user").mkdir(parents=True)
        (profile / "user/registrymodifications.xcu").write_text(PROFILE)
        output = root / "pdf"
        output.mkdir()
        command = [
            "libreoffice",
            f"-env:UserInstallation={profile.as_uri()}",
            "--headless",
            "--norestore",
            "--nodefault",
            "--nolockcheck",
            "--convert-to",
            "pdf",
            "--outdir",
            str(output),
            str(source),
        ]
        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError:
            raise RuntimeError(
                "The OCR worker requires LibreOffice for Office documents"
            ) from None
        deadline = time.monotonic() + 180
        try:
            while True:
                check()
                if time.monotonic() >= deadline:
                    raise DocumentInputError("Office conversion exceeded its deadline")
                try:
                    code = process.wait(timeout=0.2)
                    break
                except subprocess.TimeoutExpired:
                    continue
        finally:
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass  # The process exited between poll and kill.
                process.wait()
        pdf = output / (source.stem + ".pdf")
        if code or not pdf.is_file():
            raise DocumentInputError("Office document could not be rendered to PDF")
        with pdf.open("rb") as handle:
            data = handle.read(max_bytes + 1)
        if not 0 < len(data) <= max_bytes or not data.startswith(b"%PDF-"):
            raise DocumentInputError(
                "Rendered Office document is invalid or exceeds the PDF size limit"
            )
        check()
        return data
