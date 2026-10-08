# Visual Detection Prompt

## Goal
Understand the chronological video sequence from camera `{camera_id}`: describe what is happening, what changed within the sampled interval, and what risks may develop next. Also decide whether the active visual targets are present or active. Record quiet scenes as well as matches.

## Targets
{target_description}

## Current analysis goal
{attention_instruction}

When an operator attention request is present, use it as the primary target goal for this frame batch, replacing the default target focus above. Inspect the requested region and condition first, while continuing to describe the scene and forecast evidenced risks. Describe evidence relevant to that goal even when none of the default targets is detected. If no attention request is present, use the configured targets. The goal does not suppress the scene account or change the evidence restrictions.

## Instructions
- Count only real visible subjects or activity.
- The default monitoring goal is a visible person. One person alone, standing or moving, meets this goal; a group is not required. Describe what each visible person is doing, where they are, and any activity changes supported by the sampled sequence. Preserve that activity in detections, activity_description and scene_understanding for Markdown history. Text, speech, reflections and shadows alone do not qualify. An operator-supplied goal replaces this condition.
- For a confirmed match, return `goal_event` with 1-based `start_frame`, `end_frame`, and `evidence_frame` indices in the selected sequence. Choose a frame that visibly supports the match, within that interval. For no match return null. These indices bind the notification time and attached image; do not guess an unsampled onset.
- Report each detection with observable label, category, useful visible color, position in the scene, activity, and confidence.
- Keep uncertainty explicit and grounded in visible evidence.
- In `scene_understanding`, describe the visible activity and temporal changes independently of target matches. In `uncertainties`, state occlusion, sampling gaps, insufficient motion evidence and other limits.
- In `risk_predictions`, forecast only plausible near-term outcomes supported by visible physical conditions or sampled motion. Each forecast must include `risk`, `visible_evidence`, `time_horizon`, `confidence` (0 to 1), `severity` (low, medium or high), and `recommended_review`. These are predictions, never events that already happened. Give at most eight forecasts, or an empty list when no forecast is supported. Do not invent speeds, distances, identities or intent. An empty list does not certify safety.
- Prefer a short qualitative horizon such as "if the observed movement continues in the next few seconds" when exact timing cannot be established. Recommend human review, not autonomous physical action.
- Separate a clearly observed match, a possible match, and no visible match. For a possible match, name the visual ambiguity in `summary` or `detection_report` so the operator can decide whether to focus or continue watching.
- If the goal asks whether something newly appeared, compare frames in this batch only when they show a reliable before-and-after view. Otherwise describe the current frame and say that first appearance cannot be established.
- For a corridor or walkway blockage goal, inspect the visible travel path. Count equipment, carts, packages, debris, or people as a match only when they visibly obstruct that path; describe their location and how much of the path appears obstructed. If the view cannot show enough of the path to judge, report uncertainty rather than a clear or blocked verdict.

## Restrictions
- Ignore shadows, reflections, signage text, and static background clutter unless directly relevant to the active analysis goal. Stationary objects on the floor are relevant when the operator asks to find foreign objects, debris, or obstructions.
- Set detected_target and detection_count from evidence matching the active goal. Unrelated people or routine activity do not count as matches. If the requested object is absent or unclear, say so without inventing a finding.
- Do not infer identity, intent, or off-camera facts.

## Return Format
Reason about the sequence, then return your final answer in `<answer>` tags as JSON with these keys: detected, detected_target, detection_count, detections, confidence, summary, detection_report, activity_description, detected_types, detected_colors, appearance_notes, risk_level, visible_subjects, scene_understanding, risk_predictions, and uncertainties. Keep private reasoning out of the final JSON; provide only concise visible evidence for forecasts.

`summary`, `detection_report`, and `activity_description` must be plain-language strings, not lists or objects. Keep confidence and risk in their separate JSON fields.

Also return `goal_event` alongside the listed keys.

`risk_level` must be one of: low, medium, high.
