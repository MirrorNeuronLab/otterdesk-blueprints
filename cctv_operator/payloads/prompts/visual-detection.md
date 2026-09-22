# Visual Detection Prompt

## Goal
Inspect the image from camera `{camera_id}` and decide whether the active visual targets are present or active.

## Targets
{target_description}

## Current analysis goal
{attention_instruction}

When an operator attention request is present, use it as the primary analysis goal for this frame batch, replacing the default target focus above. Describe evidence relevant to that goal even when none of the default targets is detected. If no attention request is present, use the configured targets. The goal changes what to inspect; it does not change the evidence restrictions or required JSON format.

## Instructions
- Count only real visible subjects or activity.
- Report each detection with observable label, category, useful visible color, position in the scene, activity, and confidence.
- Keep uncertainty explicit and grounded in visible evidence.

## Restrictions
- Ignore shadows, reflections, signage text, and static background clutter unless directly relevant to the active analysis goal. Stationary objects on the floor are relevant when the operator asks to find foreign objects, debris, or obstructions.
- Set detected_target and detection_count from evidence matching the active goal. Unrelated people or routine activity do not count as matches. If the requested object is absent or unclear, say so without inventing a finding.
- Do not infer identity, intent, or off-camera facts.

## Return Format
Return only JSON with these keys: detected, detected_target, detection_count, detections, confidence, summary, detection_report, activity_description, detected_types, detected_colors, appearance_notes, risk_level, and visible_subjects.

`summary`, `detection_report`, and `activity_description` must be plain-language strings, not lists or objects. Keep confidence and risk in their separate JSON fields.

`risk_level` must be one of: low, medium, high.
