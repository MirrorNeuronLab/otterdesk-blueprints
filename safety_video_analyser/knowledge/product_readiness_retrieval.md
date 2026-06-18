# Safety Video Retrieval Playbook

## Useful Retrieval Queries

- What evidence was actually visible in the staged video file, and which claims must remain uncertain?
- Which observations are safety relevant without becoming an automated enforcement decision?
- What should the final report include when the visual model has low confidence or only metadata-level evidence?

## Evidence Checklist

Ground every finding in a file name, frame range, timestamp, or explicit model observation when available. If the run only has staged-file metadata, say that no frame-level hazard was confirmed and recommend human review of the source footage. Do not turn file names into facts; a file named `ladder.mp4` is only a routing clue unless frame analysis supports it.

The assistant may summarize likely review themes such as personal protective equipment, blocked exits, slips and trips, moving vehicles, hot work, ladder use, restricted areas, and unattended machinery. It must mark each as `observed`, `not_observed`, or `needs_review` rather than implying a binary pass/fail.

## Output Guidance

The final artifact should contain an executive summary, evidence list, confidence, next steps, and human-review caveats. Recommend actions such as "review timestamp 00:01:20-00:01:45" or "request a higher-resolution clip" instead of operational commands. Safety decisions, discipline, and regulatory conclusions remain human responsibilities.
