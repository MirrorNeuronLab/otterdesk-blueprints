"""Index complete camera accounts and their original window JPEGs in Membrane."""

import hashlib
import json
import re
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from itertools import zip_longest

from mn_context_engine_sdk import MediaReference
from mn_context_engine_sdk.intelligent_system import MarkdownDocumentAdapter
from mn_sdk.blueprint.memory import source_text_query

from .history_encoder import CameraEmbeddings
from .caption_store import timestamp

PRINCIPAL = "cctv-observer"
RELATIVE = re.compile(r"\b(?:past|last|previous)\s+(?:(an?|one|two|three|\d{1,4})\s+)?(minute|hour|day)s?\b", re.I)


def search_interval(question, after="", before="", *, clock=None):
    match = RELATIVE.search(question)
    if match and not after and not before:
        count = match[1] or "one"
        number = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3}.get(count.lower())
        number = number if number is not None else int(count)
        end = clock or datetime.now(timezone.utc)
        after = (end - timedelta(**{match[2].lower() + "s": number})).isoformat()
        before = end.isoformat()
    after, before = (timestamp(bound) if bound else "" for bound in (after, before))
    if after and before and after > before:
        raise ValueError("The history interval ends before it starts.")
    return after, before


class VisualHistory:
    def __init__(self, config, store, *, embeddings=None):
        self.config, self.store = config, store
        self.embeddings = embeddings if embeddings is not None else CameraEmbeddings()
        self.model = json.dumps([self.embeddings.metadata[key] for key in ("model", "tokenizer")])
        identity = json.dumps([store.job_id, store.source_id]).encode()
        self.scope = {"job_id": "camera-" + hashlib.sha256(identity).hexdigest(), "run_id": store.run_id}

    @contextmanager
    def session(self):
        session = source_text_query(self.config, principal=PRINCIPAL, scope=self.scope, timeout=8)
        if session is None:
            raise ValueError("Camera history requires the Job's Membrane source corpus.")
        try:
            yield session
        finally:
            session.close()

    def index_next(self):
        caption = self.store.next_to_index(self.model)
        if caption is None:
            return False
        try:
            self._index(caption)
        except Exception:
            self.store.retry_index(caption["id"])
            raise
        return True

    def _index(self, caption):
        identity = hashlib.sha256(caption["id"].encode()).hexdigest()
        provenance = [{"caption": caption["id"], "run_id": caption["run_id"],
                       "start_time": caption["start_time"], "end_time": caption["end_time"],
                       "source_ref": caption["source_refs"][0]}]
        with self.session() as session:
            corpus = session.corpus
            # Embed what was described. The requested goal is not an observation.
            corpus.add(caption["content"], source_id="window-" + identity, path=identity + ".md",
                       event_id="window-" + identity, adapter=MarkdownDocumentAdapter(),
                       allow=[PRINCIPAL], upstream=provenance)
            jpeg = None
            if snapshot := caption.get("snapshot"):
                jpeg = self.store.frame(caption["id"])
                ref = MediaReference.from_bytes(jpeg, uri=f"artifact://cctv/{identity}.jpg", mime_type="image/jpeg")
                if ref.sha256 != snapshot["sha256"]:
                    raise ValueError("The saved window snapshot has changed.")
                corpus.add_media(ref, source_id="frame-" + identity, path=identity + ".jpg",
                                 event_id="frame-" + identity, description=caption["content"][:1800],
                                 allow=[PRINCIPAL], upstream=[*provenance, {"received_at": snapshot["received_at"]}])
            def load_media(reference):
                reference.verify(jpeg)
                return jpeg
            indexed = corpus.units.index(self.embeddings, media_loader=load_media)
            sources = corpus.catalog()["sources"]
            if (indexed["indexed_units"] < len(sources) or
                    list(indexed["model_identity"]) != [*json.loads(self.model), 768]):
                raise ValueError("Membrane did not index all camera sources with EmbeddingGemma 2.")
            # Advance only after both text and image vectors have been acknowledged.
            for source in sources:
                if source["path"].endswith(".jpg"):
                    source["snapshot"] = snapshot
            self.store.indexed(caption["id"], self.model, sources)

    def search(self, question, after, before):
        rows = self.store.index_scope(after, before, self.model)
        selected = {}
        indexed = 0
        partial_window = False
        for row in rows:
            if row["sources"] is None:
                continue
            indexed += 1
            for source in json.loads(row["sources"]):
                received = (source.get("snapshot") or {}).get("received_at")
                if received and ((after and received < after) or (before and received > before)):
                    continue
                if not received and ((after and row["start_time"] < after) or (before and row["end_time"] > before)):
                    # A window-level caption cannot place the subject on either side of the boundary.
                    partial_window = True
                    continue
                selected[source["source_id"]] = (row["id"], source)
        result = {"observations": [], "total": len(rows), "indexed": indexed, "after": after, "before": before}
        if partial_window:
            result["limitation"] = "Captions spanning the edge of the interval could not place a sighting inside it."
        if not selected:
            return result
        image_count = sum("snapshot" in source for _, source in selected.values())
        if max(image_count, len(selected) - image_count) > 5000:
            return {**result, "limitation": "Choose a shorter time range to search these observations."}
        # Source units were registered and embedded on the write path. Search the native
        # index directly, without reading or re-registering thousands of originals per question.
        query = RELATIVE.sub("", question).strip(" .?,") or question
        vector = self.embeddings.embed_query(query)
        # Repeated generic captions should not outvote a relevant image. Ask Membrane
        # to rank actual images semantically and caption units with native hybrid search.
        lanes = []
        with self.session() as session:
            for media in (True, False):
                ids = [sid for sid, (_, src) in selected.items() if bool(src.get("snapshot")) == media]
                if not ids:
                    continue
                found = session.client.command("discover_source_units", request={
                    "query": query, "sources": ids, "mode": "semantic" if media else "hybrid",
                    "query_vector": vector["vector"], "model": vector["model"], "tokenizer": vector["tokenizer"],
                    "limit": 8, "candidate_limit": 32,
                })
                if found.get("unresolved") or found.get("status") == "incomplete":
                    result["limitation"] = "Membrane reported incomplete index coverage."
                elif found.get("status") not in ("ready", "not_found_in_searched_scope"):
                    raise ValueError("Membrane could not search the selected interval.")
                lanes.append(found["candidates"])
        admitted = set()
        for hit in (hit for pair in zip_longest(*lanes) for hit in pair if hit):
            identity, source = selected[hit["source_id"]]
            snapshot = source.get("snapshot")
            if (hit["source_revision"] != source["revision"] or hit["source_sha256"] != source["sha256"]
                    or (hit.get("media") or {}).get("sha256") != (snapshot or {}).get("sha256")):
                raise ValueError("Membrane returned a different source revision.")
            if identity not in admitted:
                caption = self.store.saved(identity, current_run=False)
                if not snapshot and hashlib.sha256(caption["content"].encode()).hexdigest() != source["sha256"]:
                    raise ValueError("The indexed window caption has changed.")
                result["observations"].append({**caption, "matched_via": "image" if snapshot else "caption"})
                admitted.add(identity)
            if len(admitted) == 4:
                break
        return result
