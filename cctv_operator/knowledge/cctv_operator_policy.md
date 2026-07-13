# CCTV Operator Policy

Use this guidance as local retrieval context for approved local video monitoring.

## Evidence Grounding

- Tie detections to frame source, timestamp or position, target class, confidence, bounding or position data, and alert-policy state.
- Separate observed visual facts from safety, access, or disciplinary conclusions.
- Preserve source mode/name, recording position or observation time, cooldown, and repeated-detection status in the review packet.

## Review Checks

- Flag missing recordings, unavailable streams, low-confidence detections, ambiguous targets, stale frames, decode/model failures, and alert suppression.
- Require human review before external alerts, enforcement actions, or safety decisions.
- Keep attention instructions and configured visual targets visible in artifacts.

## Tool Boundaries

- Video sampling and visual model tools can detect configured targets; they do not establish intent or policy violations.
- If a source or model fails, record the failure. Never hide it by switching to a demo source or CPU decoder.
