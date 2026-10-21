"""Native cumulative report projection from immutable observed camera results."""

import json

from mn_sdk.integrations.block_publication_files import publish_files
from mn_sdk_common.publication import ArtifactWrite

from .reporting import final_artifact, markdown_report, merge_report


def process(block, work):
    reference = work["payload"].get("observation")
    if (not isinstance(reference, dict) or reference.get("kind") != "cctv_observation"
        or reference.get("version") != "mn.committed_json/v1"):
        raise ValueError("CCTV reports require a committed native observation")
    observation = block.store.read(reference)
    if (not isinstance(observation, dict) or set(observation) != {"schema", "scope", "state", "events"}
        or observation["schema"] != "otterdesk.cctv.observation.v1"
        or observation["scope"] != {"job_id": block.job_id, "run_id": block.run_id}
        or not isinstance(observation["state"], dict) or not isinstance(observation["events"], list)):
        raise ValueError("CCTV observation schema or run scope differs")
    previous = work["state"].get("report")
    if previous is not None and (not isinstance(previous, dict) or previous.get("kind") != "cctv_report"
        or previous.get("version") != "mn.committed_bytes/v1"):
        raise ValueError("Cumulative CCTV history requires its committed report reference")
    report = merge_report(json.loads(block.store.read_bytes(previous)) if previous else {},
        observation["events"], observation["state"])
    encoded = (json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    publication = publish_files(block, [
        ArtifactWrite("report", "cctv_report.json", encoded, kind="cctv_report", authoritative=True),
        ArtifactWrite("markdown", "cctv_report.md", markdown_report(report).encode(), kind="markdown", authoritative=True),
        ArtifactWrite("decision", "final_artifact.json", (json.dumps(final_artifact(report), indent=2, sort_keys=True) + "\n").encode(),
            kind="json", authoritative=True)])
    state = {"report": publication["files"]["cctv_report.json"]}
    summary = {"frames_analyzed": report["frames_analyzed"], "detection_count": report["detection_count"],
        "report": state["report"], "report_paths": ["cctv_report.json", "cctv_report.md", "final_artifact.json"]}
    return {"state": state, "outputs": {"published_files": publication},
        "emissions": [{"port": "ready", "value": summary}],
        "events": [{"type": "cctv_operator_report_ready", "payload": {
            "frames_analyzed": report["frames_analyzed"], "detection_count": report["detection_count"], "summary": "Report updated"}}]}
