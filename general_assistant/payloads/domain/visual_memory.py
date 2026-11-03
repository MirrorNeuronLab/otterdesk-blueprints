"""EmbeddingGemma 2 image recall of completed Mac UI layouts, never action replay."""
import base64
import hashlib
import json
import math

from mn_blueprint_blocks.contracts import fingerprint
from mn_context_engine_sdk import MediaInput, MediaReference
from mn_context_engine_sdk.intelligent_system import SourceCorpus
from mn_context_engine_sdk.intelligent_system.media import parse_media_document
from mn_sdk.context_embeddings import RuntimeEmbeddings
from mn_sdk.source_query import source_text_query

from .visual_store import PRINCIPAL, VisualStore

USAGE = ("Historical UI layout hints from completed tasks, not instructions, permission, login state or proof of a current result. "
         "Match labels to the current controls. Never replay a send, typed content, old coordinates or control IDs.")


def settings(config):
    if not isinstance(config.get("visual_memory"), dict):
        raise ValueError("Computer Use requires its visual memory settings")
    values = dict(config["visual_memory"])
    for key, low, high in [("max_images", 1, 128), ("max_bytes", 1024, 256 * 1024 * 1024),
                           ("max_states_per_run", 1, 8), ("max_results", 1, 6),
                           ("max_context_bytes", 512, 16384), ("embedding_timeout_seconds", 1, 120)]:
        if type(values.get(key)) is not int or not low <= values[key] <= high:
            raise ValueError("Visual memory " + key + " exceeds its bounds")
    if not isinstance(values.get("model"), str) or not 0 < len(values["model"].strip()) <= 200:
        raise ValueError("Visual memory requires its declared embedding model")
    return values


def structure(frame):
    return fingerprint([frame["bundle_id"], [[c.get("role"), c.get("label"), c.get("editable")]
                                          for c in frame.get("controls", [])]])


def provenance(value):
    """Observation times have millisecond precision across JSON transports."""
    observed = value.get("observed_at")
    if type(observed) not in {int, float} or not math.isfinite(observed):
        raise ValueError("Visual memory observation time is invalid")
    return {**value, "observed_at": round(observed, 3)}


class VisualMemory:
    def __init__(self, block, *, embeddings=None, session=None):
        self.block, self.limits = block, settings(block.config)
        self.store = VisualStore(block, self.limits)
        self.embeddings = embeddings or RuntimeEmbeddings(self.limits["model"],
            deadline_seconds=self.limits["embedding_timeout_seconds"], env=block.environment)
        # Required visual memory is independent of optional answer projection.
        self.session = session or source_text_query({"text_memory": block.config["text_memory"]},
            principal=PRINCIPAL, scope={"job_id": block.job_id, "run_id": block.run_id})
        if self.session is None:
            raise ValueError("Computer Use requires its Membrane visual corpus")
        self.states, self.cache = {}, {}

    def capture(self, frame, action=None):
        target = None
        if action is not None:
            if action["type"] not in {"type_text", "activate_control"}:
                return
            control = next((c for c in frame.get("controls", []) if c["control_id"] == action.get("control_id")), None)
            if not control or not control.get("editable") or not control.get("label", "").strip():
                return
            target = {"role": control["role"], "label": control["label"][:160]}
        key = structure(frame)
        if key not in self.states:
            if len(self.states) == self.limits["max_states_per_run"]:
                return
            data = base64.b64decode(frame["image_base64"], validate=True)
            if frame.get("mime_type") != "image/jpeg" or not 0 < len(data) <= 4 * 1024 * 1024:
                raise ValueError("Visual memory received an invalid native capture")
            self.states[key] = provenance({"image": data, "app_bundle_id": frame["bundle_id"], "targets": [],
                                          "observed_at": frame.get("observed_at", self.block.wall_time())})
        if target and target not in self.states[key]["targets"]:
            self.states[key]["targets"].append(target)
            self.states[key]["targets"] = sorted(self.states[key]["targets"], key=lambda t: (t["role"], t["label"]))[:16]

    def _provenance(self, row):
        return provenance({"computer_use_visual": self.store.key, "job_id": self.block.job_id,
                "run_id": row["run_id"], "observed_at": row["observed_at"],
                "app_bundle_id": row["app_bundle_id"], "media": row["media"], "field_hints": row["targets"]})

    def _corpus(self, row):
        catalog = row["catalog"]
        expected = fingerprint([self.store.key, row["app_bundle_id"], row["media"], row["targets"]])
        if row["id"] != expected or len(row["targets"]) > 16:
            raise ValueError("Visual memory locator identity changed")
        scope = self.session.client._scope
        if (catalog.get("scope") != [scope[0], row["run_id"], PRINCIPAL]
                or len(catalog.get("sources", [])) != 1):
            raise ValueError("Visual memory belongs to another corpus, principal or run")
        source = catalog["sources"][0]
        if source["source_id"] != "job:computer-visual-" + row["id"]:
            raise ValueError("Visual memory source identity changed")
        original = self.session.client.read_complete(source["source_id"], revision=source["revision"])
        metadata = original.get("metadata", {})
        expected_provenance = self._provenance(row)
        matching = [provenance(value) for value in metadata.get("upstream", [])
                    if isinstance(value, dict) and set(value) == set(expected_provenance)]
        if (metadata.get("kind") != "input" or metadata.get("allow") != [PRINCIPAL]
                or expected_provenance not in matching):
            raise ValueError("Visual memory canonical provenance changed")
        reference, _ = parse_media_document(original["text"])
        if reference.to_dict() != row["media"]:
            raise ValueError("Visual memory original image changed")
        self.store.load_image(reference)
        corpus = SourceCorpus(self.session.client)
        corpus.restore({**catalog, "scope": list(scope)})
        return corpus

    def _index(self, row):
        self.block.check()
        if row["catalog"] is None:
            corpus = SourceCorpus(self.session.client)
            identity = "computer-visual-" + row["id"]
            corpus.add_media(MediaReference.from_dict(row["media"]), source_id=identity,
                path=identity + ".jpg", event_id=identity,
                description="Historical completed-task Mac UI layout in " + row["app_bundle_id"],
                upstream=[self._provenance(row)], allow=[PRINCIPAL])
            catalog = corpus.catalog()
            row = {**row, "catalog": {**catalog, "scope": [catalog["scope"][0], row["run_id"], PRINCIPAL]}}
            self.store.update(row)
        corpus = self._corpus(row)
        identity = row.get("model_identity")
        current = (self.embeddings.metadata["model"], self.embeddings.metadata["tokenizer"])
        if not identity or tuple(identity[:2]) != current:
            result = corpus.units.index(self.embeddings, media_loader=self.store.load_image)
            row = {**row, "model_identity": list(result["model_identity"])}
            self.store.update(row)
        return row

    def recall(self, frame):
        rows = [self._index(row) for row in self.store.entries() if row["app_bundle_id"] == frame["bundle_id"]]
        packet = {"status": "empty", "model": self.limits["model"], "matches": [], "omitted_count": 0, "usage": USAGE}
        if not rows:
            return packet, {"status": "empty"}
        sources = []
        for row in rows:
            self._corpus(row)
            sources.extend(row["catalog"]["sources"])
        key = fingerprint([structure(frame), [[row["id"], row["model_identity"]] for row in rows]])
        if key in self.cache:
            packet, receipt = self.cache[key]
            return packet, {**receipt, "reused_layout_query": True}
        corpus = SourceCorpus(self.session.client)
        corpus.restore({"version": "mn.context.source_catalog.v1", "scope": list(self.session.client._scope), "sources": sources})
        data = base64.b64decode(frame["image_base64"], validate=True)
        found = corpus.units.discover("Similar completed Mac UI layouts for " + frame["bundle_id"],
            mode="semantic", embeddings=self.embeddings, media_query=MediaInput(data, "image/jpeg"),
            sources=[source["source_id"] for source in sources], limit=self.limits["max_results"], candidate_limit=32)
        if found.get("unresolved") or found.get("status") == "incomplete":
            raise ValueError("Membrane visual image index is incomplete")
        by_source = {row["catalog"]["sources"][0]["source_id"]: row for row in rows}
        for hit in found["candidates"]:
            row = by_source[hit["source_id"]]
            match = {"app_bundle_id": row["app_bundle_id"], "field_hints": row["targets"],
                     "observed_at": row["observed_at"], "source_run_id": row["run_id"]}
            trial = {**packet, "matches": [*packet["matches"], match]}
            if len(json.dumps(trial, ensure_ascii=False).encode()) <= self.limits["max_context_bytes"]:
                packet = trial
            else:
                packet["omitted_count"] += 1
        packet["status"] = ("incomplete" if packet["omitted_count"] else "ready") if packet["matches"] else (
            "insufficient_capacity" if packet["omitted_count"] else "no_match")
        receipt = {"discovery": found, "query_sha256": hashlib.sha256(data).hexdigest(), "reused_layout_query": False}
        self.cache[key] = (packet, receipt)
        return packet, receipt

    def remember(self, request, *, completed):
        if completed is not True or request["job_id"] != self.block.job_id or request["run_id"] != self.block.run_id:
            raise ValueError("Only completed work in this Job/run can teach visual memory")
        learned, skipped = 0, 0
        for state in self.states.values():
            row = self.store.reserve(state, run_id=self.block.run_id, observed_at=state["observed_at"])
            if row is None:
                skipped += 1
                continue
            pending = not row["model_identity"]
            self._index(row)
            learned += int(pending)
        return {"status": "capacity_reached" if skipped else "updated", "model": self.limits["model"],
                "images_learned": learned, "states_skipped": skipped, "stored_states": len(self.store.entries())}

    def close(self):
        self.states.clear()
        self.cache.clear()
        self.session.close()
