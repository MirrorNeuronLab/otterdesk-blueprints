# Safety Video Review Policy

Use this guidance as local retrieval context for workplace safety-video review.

## Evidence Grounding

- Tie every safety observation to staged media, model output, timestamp, and routing metadata when available.
- Separate visible observations from inferred causes, policy conclusions, or disciplinary recommendations.
- Keep media handling local and preserve BlobRef or file references for review.

## Review Checks

- Flag missing video, unsupported model route, low-quality footage, incomplete timestamps, and ambiguous safety-relevant activity.
- Require human safety review before operational decisions, alerts, or compliance conclusions.
- Preserve model placement and GPU routing evidence when diagnosing failures.

## Tool Boundaries

- Visual models and report generators assist review only.
- If the video model is unavailable or uncertain, record the blocker instead of fabricating observations.
