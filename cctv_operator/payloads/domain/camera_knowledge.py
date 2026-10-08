"""Author sampled visual knowledge as typed Markdown, retaining complete detail."""

import json


def _cell(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False).replace("|", "\\u007c")


def observation_record(value):
    from mn_context_engine_sdk.intelligent_system import RuntimeRecord

    # Short typed facts support chronology/filtering. Complete model accounts,
    # nested detections and the instruction remain in the same authored unit.
    names = (
        "camera_id", "source_key", "memory_family", "run_id", "frame_seq",
        "batch_id", "instruction_revision", "confidence", "risk_level",
        "detection_count", "selected_count", "continuous_coverage",
    )
    facts = {name: value[name] for name in names}
    details = [name for name in value if name not in {*names, "observation_id", "observed_at", "qualification", "camera_node_id", "batch_node_id"}]
    notes = "Complete sampled account; no identity, intent or continuous coverage is established. "
    notes += "Risk predictions describe possible future outcomes, not observed events; review the linked frames.\n\n"
    notes += "### Observed activity\n\n" + str(value.get("scene_understanding") or value.get("summary") or "No scene account.") + "\n\n"
    notes += "### Predicted risks\n\n"
    for prediction in value.get("risk_predictions") or []:
        notes += (f"- {prediction['risk']} ({prediction['severity']}, confidence {prediction['confidence']:.0%}); "
                  f"horizon: {prediction['time_horizon']}. Visible evidence: {prediction['visible_evidence']}. "
                  f"Review: {prediction['recommended_review']}. Prediction, not an observed event.\n")
    notes += "\n### Complete account and provenance\n\n"
    notes += "| detail | value |\n| --- | --- |\n"
    notes += "".join(f"| {_cell(name)} | {_cell(value[name])} |\n" for name in details)
    camera_node = "camera-" + value["camera_node_id"]
    observation_node = "observation-" + value["observation_id"]
    relations = [(camera_node, "OBSERVED", observation_node)]
    if value["frame_batch_ref"]:
        relations.append((observation_node, "EVIDENCED_BY", "batch-" + value["batch_node_id"]))
    return RuntimeRecord(
        observation_node, "Sampled camera observation", value["observed_at"],
        value["qualification"], facts, notes=notes, relations=tuple(relations),
    )
