"""Typed Cosmos generation contract; semantic evidence checks remain downstream."""

from .site_monitoring import context


def response_format(frame_count, config):
    def record(properties):
        return {"type": "object", "properties": properties,
                "required": list(properties), "additionalProperties": False}

    def array(items, **limits):
        return {"type": "array", "items": items, **limits}

    text = {"type": "string", "minLength": 1, "maxLength": 200}
    score = {"type": "number", "minimum": 0, "maximum": 1}
    frame = {"type": "integer", "minimum": 1, "maximum": frame_count}
    # NIM's XGrammar backend rejects uniqueItems. Frame uniqueness and
    # cross-field evidence semantics stay in the downstream domain validators.
    frames = array(frame, minItems=1, maxItems=frame_count)
    rules = [rule["id"] for rule in context(config)["rules"]]
    schema = record({
        "detected_target": {"type": "boolean"},
        "detections": array(record({
            "label": {**text, "maxLength": 80}, "category": {**text, "maxLength": 80},
            "color": {**text, "maxLength": 60}, "position": {**text, "maxLength": 160},
            "activity": {**text, "maxLength": 160}, "confidence": score,
        }), maxItems=20),
        "confidence": score,
        "summary": {**text, "maxLength": 300},
        "scene_understanding": {**text, "maxLength": 1800},
        "risk_predictions": array(record({
            "risk": text, "visible_evidence": {**text, "maxLength": 300},
            "time_horizon": {**text, "maxLength": 120},
            "confidence": score, "severity": {"enum": ["low", "medium", "high"]},
            "recommended_review": text, "evidence_frames": frames,
        }), maxItems=2),
        "uncertainties": array(text, maxItems=8),
        "goal_event": {"anyOf": [{"type": "null"}, record({
            "start_frame": frame, "end_frame": frame, "evidence_frame": frame,
        })]},
        "helmet_observations": array(record({
            "helmet_status": {"enum": ["worn", "not_worn", "uncertain"]},
            "head_visible": {"type": "boolean"}, "evidence_frame": frame,
            "visible_evidence": {**text, "maxLength": 500},
        }), maxItems=32),
        "site_findings": array(record({
            "rule_id": {"enum": rules} if rules else text,
            "status": {"enum": ["observed", "possible", "not_observed"]},
            "confidence": score, "visible_evidence": {**text, "maxLength": 800},
            "evidence_frames": frames,
        }), maxItems=len(rules)),
    })
    return {"type": "json_schema", "json_schema": {
        "name": "cctv_scene_observation", "strict": True, "schema": schema,
    }}
