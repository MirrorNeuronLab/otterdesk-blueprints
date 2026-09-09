# Visual Detection Prompt

## Goal
Inspect the image from camera `{camera_id}` and decide whether configured visual targets are present or active.

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
- Ignore shadows, reflections, signage text, static background clutter, and uncertain guesses unless directly relevant to the configured targets.
- Do not infer identity, intent, or off-camera facts.

## Return Format
Return only JSON with these keys: detected, detected_target, detection_count, detections, confidence, summary, detection_report, activity_description, detected_types, detected_colors, appearance_notes, risk_level, and visible_subjects.

`summary`, `detection_report`, and `activity_description` must be plain-language strings, not lists or objects. Keep confidence and risk in their separate JSON fields.

`risk_level` must be one of: low, medium, high.
