"""Deterministic case-file and mbox discovery."""

from __future__ import annotations

from email import policy
from email.message import Message
from email.parser import BytesParser
import hashlib
import mailbox
import shutil
import tempfile
import mimetypes
from pathlib import Path
from typing import Iterable, Iterator

from rfm_platform.documents import DocumentIndex, IngestManifest

from ..models import CaseDocument


class CorpusIngestError(RuntimeError):
    pass


_TEXT_SUFFIXES = {
    ".txt",
    ".csv",
    ".md",
    ".json",
    ".jsonl",
    ".xml",
    ".html",
    ".htm",
    ".log",
}
_SKIP_PARTS = {".rgx", ".git", "__pycache__", ".venv", "target", "var"}


class CaseCorpus:
    def __init__(self, root: str | Path, access_scope: str = "default") -> None:
        self.root = Path(root).expanduser().resolve()
        self.access_scope = access_scope.strip()
        if not self.root.is_dir():
            raise CorpusIngestError(f"corpus root does not exist: {self.root}")
        if not self.access_scope:
            raise CorpusIngestError("access_scope must be non-empty")

    def scan(self) -> tuple[CaseDocument, ...]:
        documents: list[CaseDocument] = []
        for path in self._source_paths():
            if path.suffix.casefold() == ".mbox":
                documents.extend(self._scan_mbox(path))
            elif path.suffix.casefold() == ".eml":
                message = BytesParser(policy=policy.default).parsebytes(path.read_bytes())
                text = self._message_text(message)
                relative = path.relative_to(self.root).as_posix()
                documents.append(CaseDocument(source_id=f"case:{relative}", relative_path=relative, media_type="message/rfc822", content_sha256=hashlib.sha256(text.encode()).hexdigest(), size_bytes=path.stat().st_size, text=text, access_scope=self.access_scope))
            else:
                documents.append(self._scan_file(path))
        return tuple(documents)

    def inject(self, index: DocumentIndex) -> tuple[IngestManifest, ...]:
        manifests: list[IngestManifest] = []
        for document in self.scan():
            if document.text is None:
                continue
            manifest = index.inject_bytes(
                document.text.encode("utf-8"), document.source_id, document.access_scope
            )
            if manifest.content_sha256 != document.content_sha256:
                raise CorpusIngestError(
                    f"indexed content hash mismatch for {document.source_id}"
                )
            manifests.append(manifest)
        return tuple(manifests)

    def _source_paths(self) -> Iterator[Path]:
        paths = []
        for path in self.root.rglob("*"):
            if path.is_symlink():
                raise CorpusIngestError("symbolic links are not accepted as case sources")
            if not path.is_file():
                continue
            relative = path.relative_to(self.root)
            if any(part.startswith(".") or part in _SKIP_PARTS or part.endswith(".rgx") for part in relative.parts):
                continue
            paths.append(path)
        yield from sorted(paths, key=lambda item: item.relative_to(self.root).as_posix())

    def _scan_file(self, path: Path) -> CaseDocument:
        relative = path.relative_to(self.root).as_posix()
        content = path.read_bytes()
        media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        text: str | None = None
        if path.suffix.casefold() in _TEXT_SUFFIXES or media_type.startswith("text/"):
            try:
                text = content.decode("utf-8")
            except UnicodeDecodeError:
                text = None
        if path.suffix.casefold() == ".pdf":
            from mn_pdf_extract_skill import extract_pages_from_pdf
            try:
                pages = extract_pages_from_pdf(path)
                text = "\n".join(f"Page {p['page_number']}:\n\n{p['text']}" for p in pages) if any(p["text"].strip() for p in pages) else None
            except Exception:
                # Parser failures are explicit coverage gaps. Missing dependency
                # imports above still fail preparation instead of hiding setup errors.
                text = None
        elif path.suffix.casefold() in {".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt", ".odt", ".rtf"}:
            from mn_document_reading_skill.anydoc_conversion import AnyDocConversionError, convert_with_anydoc
            try:
                text = convert_with_anydoc(path)
            except AnyDocConversionError:
                text = None
        digest_source = text.encode("utf-8") if text is not None else content
        return CaseDocument(
            source_id=f"case:{relative}",
            relative_path=relative,
            media_type=media_type,
            content_sha256=hashlib.sha256(digest_source).hexdigest(),
            size_bytes=len(content),
            text=text,
            access_scope=self.access_scope,
        )

    def _scan_mbox(self, path: Path) -> Iterable[CaseDocument]:
        relative = path.relative_to(self.root).as_posix()

        def factory(stream):
            return BytesParser(policy=policy.default).parse(stream)

        try:
            # mailbox.mbox opens files rb+ even for iteration. Parse a private copy
            # so read-only source mounts work and originals are never opened writable.
            with tempfile.TemporaryDirectory(prefix="case-mbox-") as directory:
                snapshot = Path(directory) / "mail.mbox"
                shutil.copyfile(path, snapshot)
                box = mailbox.mbox(snapshot, factory=factory, create=False)
                try:
                    messages = list(box)
                finally:
                    box.close()
        except (OSError, mailbox.Error) as exc:
            raise CorpusIngestError(f"cannot parse mbox {relative}: {exc}") from exc

        results: list[CaseDocument] = []
        for position, message in enumerate(messages):
            text = self._message_text(message)
            content = text.encode("utf-8")
            digest = hashlib.sha256(content).hexdigest()
            source_id = f"case:{relative}#message={position:06d}:{digest[:12]}"
            results.append(
                CaseDocument(
                    source_id=source_id,
                    relative_path=f"{relative}#message={position:06d}",
                    media_type="message/rfc822",
                    content_sha256=digest,
                    size_bytes=len(content),
                    text=text,
                    access_scope=self.access_scope,
                    container_source_id=f"case:{relative}",
                )
            )
        return results

    @staticmethod
    def _message_text(message: Message) -> str:
        headers = [
            f"Date: {message.get('Date', '')}",
            f"From: {message.get('From', '')}",
            f"To: {message.get('To', '')}",
            f"Cc: {message.get('Cc', '')}",
            f"Subject: {message.get('Subject', '')}",
        ]
        bodies: list[str] = []
        parts = message.walk() if message.is_multipart() else (message,)
        for part in parts:
            if part.is_multipart() or part.get_content_type() != "text/plain":
                continue
            try:
                value = part.get_content()
            except (LookupError, UnicodeDecodeError):
                payload = part.get_payload(decode=True) or b""
                charset = part.get_content_charset() or "utf-8"
                value = payload.decode(charset, errors="replace")
            bodies.append(str(value))
        return "\n".join([*headers, "", *bodies]).strip() + "\n"

