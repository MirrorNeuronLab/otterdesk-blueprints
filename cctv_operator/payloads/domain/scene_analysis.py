"""Journal the selected perception/decision composition without repair calls."""

from mn_sdk.integrations.block_model_request import model_request, model_response_metadata

from .cosmos_access import cosmos_slot
from . import frame_perception


def analyze(block, prepared, metrics, *, frames, revision):
    timings = []
    observations = []
    error = None
    if "perception_requests" in prepared:
        with cosmos_slot(block.store.run_dir):
            for index, request in enumerate(prepared["perception_requests"], 1):
                key = f"perception-frame-{index}"
                raw = model_request(block, request, key=key)
                metadata = model_response_metadata(block, request, key=key)
                timings.append(metadata)
                try:
                    observations.append(frame_perception.observation(raw, index))
                except ValueError as exc:
                    error = str(exc)
                    break
        perception_seconds = sum(item["duration_seconds"] for item in timings)
        metrics.record("caption.perception", perception_seconds * 1000,
            variant=prepared["perception_requests"][0]["model"], status="error" if error else "ok",
            sample_key=block.invocation_id + ":perception", metadata={"frames": len(timings), "instruction_revision": revision})
        if error:
            return None, {"duration_seconds": perception_seconds, "completed_at": timings[-1]["completed_at"],
                          "perception_seconds": perception_seconds, "decision_seconds": 0}, error
        request = frame_perception.decision_request(prepared, observations)
        raw = model_request(block, request, key="scene")
        metadata = model_response_metadata(block, request, key="scene")
        timings.append(metadata)
        metadata = {"completed_at": metadata["completed_at"], "duration_seconds": sum(item["duration_seconds"] for item in timings),
                    "perception_seconds": perception_seconds, "decision_seconds": metadata["duration_seconds"]}
    else:
        request = prepared["request"]
        with cosmos_slot(block.store.run_dir):
            raw = model_request(block, request, key="scene")
        metadata = model_response_metadata(block, request, key="scene")
    return raw, metadata, None
