"""Bounded CCTV stage measurements, grouped by experiment and implementation."""

import json
import hashlib
import math
import platform
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path


STAGES = {
    "stream.frame_age": "Frame availability to processing",
    "person.model_load": "RF-DETR model preparation",
    "person.preprocess": "Person frame decoding",
    "person.inference": "RF-DETR for person events",
    "person.policy": "Person episode policy",
    "person.evidence": "Person evidence persistence",
    "notice.publish": "Notice publication",
    "person.capture_to_notice": "Frame availability to person notice",
    "caption.queue_wait": "Caption queue delay",
    "caption.dispatch_wait": "Core caption dispatch delay",
    "caption.model_queue_wait": "Cosmos capacity wait",
    "caption.inference": "Cosmos video captioning",
    "memory.recall": "MN caption context retrieval",
    "memory.write": "MN caption memory publication",
    "caption.capture_to_memory": "Frame availability to caption memory",
    "rag.retrieve": "MN historical caption retrieval",
    "rag.answer": "Historical Q&A text generation",
    "caption.coverage": "Caption coverage",
    "person.coverage": "Person detector coverage",
}


class Benchmarks:
    def __init__(self, run_dir, config=None):
        settings = (config or {}).get("benchmarks") or {}
        self.path = Path(run_dir) / "benchmarks" / "stages.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.cohort = str(settings.get("cohort", "live"))[:80]
        sections = {"person_detector": ("model", "fps", "confidence_threshold", "consecutive_hits", "absence_seconds", "max_gap_seconds"),
                    "sampling": ("baseline_interval_seconds", "burst_candidate_fps", "frame_jpeg_max_width", "max_model_frames", "max_calls_per_minute", "pre_roll_seconds", "post_roll_seconds"),
                    "text_memory": ("enabled", "max_results", "max_context_bytes")}
        self.configuration = {section: {key: (config or {}).get(section, {}).get(key) for key in keys}
                              for section, keys in sections.items()}
        llm = (config or {}).get("llm") or {}
        self.configuration["models"] = {name: {key: ((llm.get("configs") or {}).get(name) or {}).get(key)
            for key in ("model", "backend", "max_tokens", "timeout_seconds", "num_retries")}
            for name in ("primary", "vision")}
        alert = (((config or {}).get("inputs") or {}).get("payload") or {}).get("alert_policy") or {}
        self.configuration["alerts"] = {key: alert.get(key) for key in ("min_confidence", "cooldown_seconds")}
        preview = ((config or {}).get("web_ui") or {}).get("preview") or {}
        self.configuration["capture"] = {key: preview.get(key) for key in ("fps", "width", "jpeg_quality")}
        self.configuration_hash = hashlib.sha256(json.dumps(self.configuration, sort_keys=True).encode()).hexdigest()
        implementation = hashlib.sha256()
        for module in sorted(Path(__file__).parent.glob("*.py")):
            implementation.update(module.name.encode())
            implementation.update(module.read_bytes())
        self.implementation_hash = implementation.hexdigest()
        self.max_samples = int(settings.get("max_samples", 10000))
        if not 100 <= self.max_samples <= 100000:
            raise ValueError("benchmarks.max_samples must be between 100 and 100000")
        with self._connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("CREATE TABLE IF NOT EXISTS samples (id INTEGER PRIMARY KEY, "
                       "at REAL, stage TEXT, variant TEXT, cohort TEXT, phase TEXT, "
                       "status TEXT, duration_ms REAL, metadata TEXT)")
            db.execute("CREATE TABLE IF NOT EXISTS settings (name TEXT PRIMARY KEY, value INTEGER)")
            retained = db.execute("SELECT value FROM settings WHERE name='max_samples'").fetchone()
            if config is None and retained:
                self.max_samples = retained[0]
            else:
                db.execute("INSERT OR REPLACE INTO settings (name,value) VALUES ('max_samples',?)", (self.max_samples,))

    def _connect(self):
        return sqlite3.connect(self.path, timeout=5)

    def record(self, stage, duration_ms, *, variant, phase="warm", status="ok", metadata=None):
        if stage not in STAGES or phase not in {"cold", "warm"} or status not in {"ok", "error", "skipped"}:
            raise ValueError("invalid CCTV benchmark measurement")
        if not math.isfinite(duration_ms) or duration_ms < 0:
            raise ValueError("benchmark duration must be finite and nonnegative")
        # Deliberate allowlist: benchmarks contain timing/configuration, never
        # camera URLs, images, captions, private prompts or exception messages.
        allowed = {"frames", "skipped_frames", "skipped_windows", "threshold", "fps", "dataset_sha256",
                   "resolution", "device", "cuda", "torch", "package", "weights_sha256",
                   "peak_gpu_bytes", "timestamp_basis", "instruction_revision"}
        values = {key: value for key, value in (metadata or {}).items() if key in allowed}
        values["host_architecture"] = platform.machine()
        values["configuration_sha256"] = self.configuration_hash
        values["implementation_sha256"] = self.implementation_hash
        with self._connect() as db:
            db.execute("INSERT INTO samples (at,stage,variant,cohort,phase,status,duration_ms,metadata) "
                       "VALUES (?,?,?,?,?,?,?,?)", (time.time(), stage, str(variant)[:240], self.cohort,
                                                 phase, status, duration_ms, json.dumps(values, allow_nan=False)))
            db.execute("DELETE FROM samples WHERE id <= (SELECT COALESCE(MAX(id),0)-? FROM samples)",
                       (self.max_samples,))

    @contextmanager
    def measure(self, stage, *, variant, phase="warm", metadata=None):
        start = time.perf_counter()
        status = "ok"
        try:
            yield
        except BaseException:
            status = "error"
            raise
        finally:
            self.record(stage, (time.perf_counter() - start) * 1000,
                        variant=variant, phase=phase, status=status, metadata=metadata)

    def summary(self):
        with self._connect() as db:
            rows = db.execute("SELECT stage,variant,cohort,phase,status,duration_ms,metadata FROM samples ORDER BY id").fetchall()
        groups = {}
        for stage, variant, cohort, phase, status, duration, metadata in rows:
            # Hardware, weights and dataset must agree before samples are pooled.
            details = json.loads(metadata)
            identity = {key: details[key] for key in ("host_architecture", "device", "cuda", "torch",
                        "package", "weights_sha256", "resolution", "dataset_sha256", "threshold", "fps",
                        "configuration_sha256", "implementation_sha256", "instruction_revision") if key in details}
            key = (stage, variant, cohort, phase, json.dumps(identity, sort_keys=True))
            group = groups.setdefault(key, {"stage": stage, "label": STAGES[stage], "variant": variant,
                "cohort": cohort, "phase": phase, "hardware_and_model": identity,
                "ok": 0, "errors": 0, "skipped": 0, "skipped_frames": 0, "skipped_windows": 0,
                "peak_gpu_bytes": None, "values": []})
            group[{"ok": "ok", "error": "errors", "skipped": "skipped"}[status]] += 1
            group["skipped_frames"] += int(details.get("skipped_frames", 0))
            group["skipped_windows"] += int(details.get("skipped_windows", 0))
            if "peak_gpu_bytes" in details:
                group["peak_gpu_bytes"] = max(group["peak_gpu_bytes"] or 0, int(details["peak_gpu_bytes"]))
            if status == "ok":
                group["values"].append(duration)
        result = []
        for group in groups.values():
            values = sorted(group.pop("values"))
            group.update(p50_ms=_percentile(values, .5), p95_ms=_percentile(values, .95),
                         max_ms=max(values) if values else None)
            result.append(group)
        return {"schema": "otterdesk.cctv.benchmarks.v1", "retained_samples": len(rows),
                "max_samples": self.max_samples, "window": "most recent retained measurements",
                "timestamp_basis": "worker frame availability, not camera sensor or desktop receipt",
                "stages": sorted(result, key=lambda row: (row["stage"], row["variant"], row["cohort"], row["phase"]))}


def _percentile(values, fraction):
    if not values:
        return None
    index = (len(values) - 1) * fraction
    lower, upper = math.floor(index), math.ceil(index)
    return round(values[lower] + (values[upper] - values[lower]) * (index - lower), 3)
