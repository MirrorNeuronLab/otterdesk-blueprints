# CCTV Operator Retrieval Playbook

## Useful Retrieval Queries

- Which visual targets and alert policy were configured for this run?
- What changed in the observed stream, and did it cross the configured confidence or cooldown thresholds?
- Which alerts were skipped, sent, or held for human notice only?

## Evidence Checklist

Treat `visual_targets` and `alert_policy` as the source of truth. A detection that is outside the configured target list should be logged as context, not escalated as an alert. When confidence is below the policy threshold, surface it as a low-confidence observation and explain which evidence would make it actionable.

For each notable event, preserve the source stream, target label, confidence, approximate frame time, bounding-region or position if available, and the decision path. Mention cooldown suppression explicitly so reviewers can distinguish "nothing happened" from "event observed but notification skipped."

## Output Guidance

The CCTV report should be audit-friendly: source mode/name, recording position or observation time, detected targets, counts, confidence, alert decision, policy thresholds, next review step, and source references. Do not imply physical security action. If Slack or websocket fan-out is disabled, say local run-store artifacts are authoritative and optional fan-out was not active.
