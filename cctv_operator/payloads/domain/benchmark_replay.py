"""Repeat person-detector comparisons against the same approved labeled frames."""

import hashlib
import json
import math
from pathlib import Path

from mn_sdk.blueprint_support import write_json

from .benchmarks import Benchmarks, _percentile
from .person_detector import RFDETRPersonDetector
from .person_events import PersonEpisodes


def load_dataset(path):
    path = Path(path).resolve()
    if path.stat().st_size > 1024 * 1024:
        raise ValueError("benchmark manifest exceeds 1 MiB")
    content = path.read_bytes()
    if len(content) > 1024 * 1024:
        raise ValueError("benchmark manifest exceeds 1 MiB")
    manifest = json.loads(content)
    rows = manifest.get("frames")
    if not isinstance(rows, list) or not 1 <= len(rows) <= 10000:
        raise ValueError("benchmark requires 1 to 10000 labeled frames")
    digest = hashlib.sha256(content)
    frames = []
    previous = -math.inf
    for row in rows:
        relative = Path(row["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("benchmark frames must be dataset-relative")
        frame = (path.parent / relative).resolve(strict=True)
        if not frame.is_relative_to(path.parent):
            raise ValueError("benchmark frame is outside the dataset")
        timestamp = row["timestamp"]
        if isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)) or not math.isfinite(timestamp) or timestamp <= previous:
            raise ValueError("benchmark frame timestamps must strictly increase")
        if type(row.get("person_present")) is not bool:
            raise ValueError("each benchmark frame requires person_present=true or false")
        size = frame.stat().st_size
        if not 1 <= size <= 2 * 1024 * 1024:
            raise ValueError("benchmark JPEG exceeds 2 MiB")
        digest.update(frame.read_bytes())
        frames.append({"path": frame, "timestamp": timestamp, "person_present": row["person_present"]})
        previous = timestamp
    events = manifest.get("person_events")
    if "person_events" in manifest and (not isinstance(events, list) or len(events) > 10000):
        raise ValueError("invalid benchmark person_events")
    previous_end = -math.inf
    for event in events or []:
        start, end = event.get("start"), event.get("end")
        if any(isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v) for v in (start, end)) or not previous_end < start <= end:
            raise ValueError("labeled person event intervals must be ordered and disjoint")
        previous_end = end
    return frames, events, digest.hexdigest()


def accuracy(predictions, truth, emitted, events):
    labeling_provided = events is not None
    events = events or []
    tp = sum(pred and label for pred, label in zip(predictions, truth))
    fp = sum(pred and not label for pred, label in zip(predictions, truth))
    fn = sum(not pred and label for pred, label in zip(predictions, truth))
    tn = sum(not pred and not label for pred, label in zip(predictions, truth))
    matched, delays, false_events = set(), [], 0
    for timestamp in emitted:
        match = next((index for index, event in enumerate(events)
                      if index not in matched and event["start"] <= timestamp <= event["end"]), None)
        if match is None:
            false_events += 1
        else:
            matched.add(match)
            delays.append((timestamp - events[match]["start"]) * 1000)
    return {"frame_presence": {"true_positive": tp, "false_positive": fp, "false_negative": fn, "true_negative": tn,
        "precision": tp / (tp + fp) if tp + fp else None, "recall": tp / (tp + fn) if tp + fn else None},
        "person_events": {"labeling_provided": labeling_provided, "matched": len(matched), "missed": len(events) - len(matched),
            "false_events": false_events if labeling_provided else None,
            "recall": len(matched) / len(events) if events else None,
            "p50_confirmation_delay_ms": _percentile(sorted(delays), .5),
            "p95_confirmation_delay_ms": _percentile(sorted(delays), .95)},
        "qualification": "Offline replay: episode confirmation delay uses labeled footage time; excludes live scheduling and notice delivery."}


def replay(dataset, output, sizes, *, threshold=.55, warmup=5, detector_factory=RFDETRPersonDetector):
    frames, events, fingerprint = load_dataset(dataset)
    output = Path(output)
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("benchmark comparison requires a new or empty output directory")
    results = []
    for size in sizes:
        directory = output / size
        metrics = Benchmarks(directory, {"benchmarks": {"cohort": fingerprint, "max_samples": 100000}})
        detector = detector_factory({"model": size, "confidence_threshold": threshold}, benchmarks=metrics)
        detector.metadata["dataset_sha256"] = fingerprint
        detector.load()
        measurement_owner = detector.benchmarks
        detector.benchmarks = None
        for _index in range(warmup):
            detector.detect(frames[0]["path"].read_bytes())
        detector.benchmarks = measurement_owner
        policy = {"consecutive_hits": 2, "absence_seconds": 2, "max_gap_seconds": 2}
        episodes = PersonEpisodes(policy)
        predictions, emitted = [], []
        for row in frames:
            people = detector.detect(row["path"].read_bytes())
            predictions.append(bool(people))
            with metrics.measure("person.policy", variant=detector.variant, metadata=detector.metadata):
                event = episodes.update(people, row["timestamp"])
            if event:
                emitted.append(event["confirmed_at"])
        result = {"model": detector.variant, "dataset_sha256": fingerprint, "frame_count": len(frames),
                  "threshold": threshold, "warmup_frames": warmup, "episode_policy": policy,
                  "accuracy": accuracy(predictions, [row["person_present"] for row in frames], emitted, events),
                  "timings": metrics.summary()}
        write_json(directory / "replay.json", result)
        results.append(result)
        del detector
        # Models are compared sequentially on the same GPU, without retaining
        # the earlier model's tensors or counting its allocations as the next.
        import gc
        gc.collect()
        import torch
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()
    write_json(output / "comparison.json", {"schema": "otterdesk.cctv.detector_comparison.v1", "results": results})
    return results
