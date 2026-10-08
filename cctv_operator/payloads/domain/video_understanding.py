"""CCTV temporal evidence and qualified risk forecasts."""

import math
from datetime import datetime, timezone


def batch_context(batch):
    timestamps = [float(row["timestamp"]) for row in batch["selected_frames"]]
    if not timestamps or any(not math.isfinite(value) or value <= 0 for value in timestamps):
        raise ValueError("video understanding requires actual frame capture timestamps")
    if timestamps != sorted(timestamps):
        raise ValueError("video frames must be in chronological order")
    return {
        "capture_started_at": datetime.fromtimestamp(timestamps[0], timezone.utc).isoformat().replace("+00:00", "Z"),
        "capture_ended_at": datetime.fromtimestamp(timestamps[-1], timezone.utc).isoformat().replace("+00:00", "Z"),
        "frame_timestamps": timestamps,
        "timestamp_basis": batch.get("timestamp_basis", "worker_capture_unix_seconds"),
    }


def temporal_prompt(prompt, context):
    times = ", ".join(f"frame {index}: {value:.3f}" for index, value in enumerate(context["frame_timestamps"], 1))
    return prompt + (
        "\n\nChronological selected video frames (worker capture Unix seconds): " + times +
        "\nThese are capture times, not the recording's original date or exact media PTS. "
        "Frames may be irregularly spaced. Use these times rather than assuming uniform motion, "
        "continuous coverage or that a looping demo is happening live at a real facility."
    )


def understanding_fields(result):
    predictions = result.get("risk_predictions", [])
    if not isinstance(predictions, list) or len(predictions) > 8:
        raise ValueError("risk_predictions must be a list of at most eight qualified forecasts")
    qualified = []
    for item in predictions:
        if not isinstance(item, dict):
            raise ValueError("risk prediction must be an object")
        required = ("risk", "visible_evidence", "time_horizon", "recommended_review")
        if any(not isinstance(item.get(key), str) or not item[key].strip() for key in required):
            raise ValueError("risk prediction requires risk, visible evidence, time horizon and recommended review")
        confidence = item.get("confidence")
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
            raise ValueError("risk prediction confidence must be a finite number between zero and one")
        severity = item.get("severity")
        if severity not in {"low", "medium", "high"}:
            raise ValueError("risk prediction severity must be low, medium or high")
        qualified.append({**{key: item[key].strip() for key in required},
                          "confidence": confidence, "severity": severity,
                          "qualification": "prediction_not_observed_event"})
    uncertainties = result.get("uncertainties", [])
    if not isinstance(uncertainties, list) or any(not isinstance(value, str) for value in uncertainties):
        raise ValueError("uncertainties must be a list of strings")
    return {"scene_understanding": str(result.get("scene_understanding") or result.get("summary") or ""),
            "risk_predictions": qualified, "uncertainties": uncertainties}
