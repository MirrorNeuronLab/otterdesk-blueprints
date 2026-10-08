"""CCTV candidate admission and resident perception composition."""

import base64
import hashlib
import math
from pathlib import Path

from mn_sdk_models.local_service import LocalModelService, local_model_request
from mn_sdk_models.embeddings import cosine
from .mobileclip import MODEL_ID, MODEL_REVISION, MobileCLIPEncoder
from mn_sdk_rag.media_archive import MediaArchive

from .conversation_snapshot import _preview_bytes
from .detection_policy import DEFAULT_MONITORING_GOAL

BINDING_FILE = "perception_binding.json"


def gate_prompts(goal):
    if goal == DEFAULT_MONITORING_GOAL:
        return (["A surveillance image with a person visible.",
                 "A person standing or walking in the scene."],
                ["An empty surveillance scene.",
                 "An empty aisle with shelves and boxes."])
    # CLIP is weak at negation. Use visual reference scenes, never pretend
    # that a prompt containing 'not <goal>' is a calibrated negative class.
    return ([goal], ["An empty surveillance scene.", "A routine surveillance scene."])


def admit_candidate(state, scores, goal, timestamp, config):
    settings = config.get("perception") or {}
    minimum = float(settings.get("similarity_threshold", .22))
    margin = float(settings.get("similarity_margin", .02))
    consecutive = int(settings.get("consecutive_hits", 2))
    retry = float(settings.get("verification_interval_seconds", 30))
    values = [scores.get("positive_similarity"), scores.get("reference_similarity"), timestamp,
              minimum, margin, retry]
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in values):
        raise ValueError("candidate scores and settings must be finite")
    if not -1 <= minimum <= 1 or not 0 <= margin <= 2 or not 1 <= consecutive <= 10 or not 1 <= retry <= 300:
        raise ValueError("candidate gate settings are invalid")
    if any(not -1 <= scores[key] <= 1 for key in ("positive_similarity", "reference_similarity")):
        raise ValueError("candidate similarity exceeds cosine bounds")
    prior = state.get("semantic_gate") or {}
    # A gap invalidates persistence, but cannot prove an ongoing event ended.
    if prior.get("goal") != goal:
        prior = {"goal": goal, "episode": int(prior.get("episode") or 0) + 1}
    gate = dict(prior)
    elapsed = timestamp - float(prior.get("timestamp") or 0)
    if elapsed > 5 or elapsed <= 0:
        gate.update(hits=0, misses=0, open=False)
    hit = scores["positive_similarity"] >= minimum and scores["positive_similarity"] - scores["reference_similarity"] >= margin
    gate["hits"] = int(gate.get("hits") or 0) + 1 if hit else 0
    gate["misses"] = 0 if hit else int(gate.get("misses") or 0) + 1
    if gate["misses"] >= consecutive and (gate.get("episode_active") or gate.get("open")):
        gate["open"] = False
        gate["episode_active"] = False
        gate["episode"] = int(gate.get("episode") or 0) + 1
        gate["last_admitted"] = 0
    gate["timestamp"] = timestamp
    if gate["hits"] >= consecutive:
        gate["open"] = True
        gate["episode_active"] = True
    admitted = bool(hit and gate.get("open") and timestamp - float(gate.get("last_admitted") or 0) >= retry)
    if admitted:
        gate["last_admitted"] = timestamp
    state["semantic_gate"] = gate
    return {"admit": admitted, "model": MODEL_ID, "episode": gate["episode"],
            "sampled_at": timestamp,
            "goal": goal, "positive_similarity": scores["positive_similarity"],
            "reference_similarity": scores["reference_similarity"],
            "threshold": minimum, "margin": margin, "interpretation": "candidate_only"}


def candidate_gate(run_dir, run_id, config, goal):
    def check(jpeg, timestamp, state):
        scores = local_model_request(Path(run_dir) / BINDING_FILE, run_id,
            {"operation": "score", "image": base64.b64encode(jpeg).decode("ascii"),
             "timestamp": timestamp, "goal": goal})
        return admit_candidate(state, scores, goal, timestamp, config)
    return check


class CCTVPerception:
    def __init__(self, run_dir, run_id, config, *, encoder=None, archive=None):
        self.config, self.run_id = config, run_id
        settings = config.get("perception") or {}
        self.encoder = encoder or MobileCLIPEncoder()
        self.archive = archive or MediaArchive(Path(run_dir) / "video_history.sqlite3",
            model_key=f"{MODEL_ID}@{MODEL_REVISION}",
            max_rows=int(settings.get("history_max_frames", 3600)),
            max_bytes=int(settings.get("history_max_bytes", 512 * 1024**2)),
            retention_seconds=float(settings.get("history_retention_seconds", 3600)))

    def request(self, payload):
        operation = payload.get("operation")
        if operation == "score":
            encoded, goal = payload.get("image"), payload.get("goal")
            if not isinstance(encoded, str) or len(encoded) > 2_800_000:
                raise ValueError("frame exceeds bounds")
            if not isinstance(goal, str) or not 0 < len(goal.strip()) <= 500:
                raise ValueError("monitoring goal is invalid")
            jpeg = base64.b64decode(encoded, validate=True)
            vector = self.encoder.encode_image(jpeg)
            positive, reference = gate_prompts(goal)
            settings = self.config.get("video_source") or {}
            timestamp = payload.get("timestamp")
            identifier = hashlib.sha256(f"{timestamp}:".encode() + jpeg).hexdigest()
            self.archive.add(identifier, timestamp, _preview_bytes(jpeg), vector,
                {"camera_id": settings.get("camera_id", "cctv"),
                 "source_profile": settings.get("profile", "external"), "run_id": self.run_id})
            return {"positive_similarity": max(cosine(vector, self.encoder.encode_text(text)) for text in positive),
                    "reference_similarity": max(cosine(vector, self.encoder.encode_text(text)) for text in reference)}
        if operation == "retrieve":
            question = payload.get("question", "")
            if not isinstance(question, str) or len(question) > 1000:
                raise ValueError("video question exceeds bounds")
            vector = self.encoder.encode_text(question) if question else None
            packet = self.archive.retrieve(vector, after=payload.get("after"), before=payload.get("before"), limit=12)
            for frame in packet["frames"]:
                frame["image"] = base64.b64encode(frame["image"]).decode("ascii")
            return packet
        raise ValueError("unsupported perception operation")

    def start(self, run_dir):
        return LocalModelService(self.request, binding_path=Path(run_dir) / BINDING_FILE, scope=self.run_id).start()
