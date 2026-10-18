"""Reviewable facility actions from retained typed observations."""
import html


def sections(observations):
    lines = ["## Facility review queue", "", "Sampled visual interpretations require operator review. A forecast is not an incident, a model confidence is not a calibrated probability, and no response was performed."]
    rows = [(o, f) for o in observations for f in o.get("site_findings", []) if f["status"] in {"observed", "possible"}]
    if not rows:
        lines += ["", "No observed/possible facility rule was retained here. Missing or unexamined rules are not clear-scene findings."]
    for observation, finding in rows:
        def text(value):
            value = html.escape(str(value)).replace("\n", " ")
            for char in "[]()*_`":
                value = value.replace(char, "\\" + char)
            return value
        lines += ["", "### " + text(finding["title"]) + " — " + text(finding["status"]),
            "Capture interval: " + text(observation.get("capture_started_at")) + " to " + text(observation.get("capture_ended_at")),
            "Visible basis: " + text(finding["visible_evidence"]),
            "Suggested review: " + text(finding["recommended_review"]),
            "Operator-supplied owner: " + text(finding["review_owner"]),
            "Evidence: " + text(observation.get("frame_batch_ref")) + " · selected frames " + ", ".join(str(r["frame"]) for r in finding["evidence_refs"]),
            "State: " + finding["review_state"] + "; severity " + finding["severity"]]
    for observation in observations:
        coverage = observation.get("site_coverage", {})
        if coverage.get("unexamined_rule_ids"):
            lines += ["", "Unexamined at " + str(observation.get("observed_at")) + ": " + ", ".join(coverage["unexamined_rule_ids"])]
    return lines
