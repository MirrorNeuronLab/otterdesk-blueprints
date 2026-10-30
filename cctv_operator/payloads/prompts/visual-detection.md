# Visual Detection Prompt

## Goal
Understand the chronological video sequence from camera `{camera_id}`: describe what is happening, what changed within the sampled interval, and what risks may develop next. Also decide whether the active visual targets are present or active. Record quiet scenes as well as matches.

## Targets
{target_description}

## Current analysis goal
{attention_instruction}

When an operator attention request is present, use it as the primary target goal for this frame batch, replacing the default target focus above. Preserve its positive or negative condition: checking whether someone is wearing a helmet is different from checking for an uncovered head. Inspect the requested region and condition first, while continuing to describe the scene and forecast evidenced risks. Describe evidence relevant to that goal even when none of the default targets is detected. If no attention request is present, use the configured targets. The goal does not suppress the scene account or change the evidence restrictions.

Evaluate the operator's actual requested condition, including negation, from the
current selected frames. Do not substitute a default target or turn a different
observation into a goal match. Set `detected_target=true` only when the requested
condition is supported, and bind `goal_event` to the supporting selected frames.
When the condition is absent or cannot be judged, return false with a null goal
event and describe the scene and uncertainty. Keep independent risk forecasts
separate from the goal-match decision.

## Instructions
- Count only real visible subjects or activity.
- When `group_presence` is a configured facility rule, two or more real people visible together in any one selected frame is an observed finding. Check this independently of helmets, movement, obstruction, or risk: a stationary or helmeted group still qualifies. Do not count one person repeated across frames as a group. Use not_observed when a clear view shows fewer than two people; use possible when occlusion or blur prevents judging the count. Report the first matching sample even if the group is already visible at startup; no earlier empty frame is required for presence. Say "A group of people is visible" and describe their location/activity; say "appeared" only when a reliable before-and-after view establishes arrival. Cite the selected frame showing the group in `site_findings`. Set `detected_target` and `goal_event` from this finding only when group presence is part of the active goal; an explicit operator goal still takes precedence.
- This sequence is admitted by a confirmed RF-DETR person sample or an explicitly configured periodic scene audit. An audit does not establish person presence. The admission signal is not a finding about helmets or any other condition. Apply the active analysis goal and supplied facility policy; do not assume every profile has a helmet goal. Mere person presence does not establish an uncovered head, path obstruction or other condition. If a helmet condition is relevant, confirm an uncovered head only when clearly visible; an occluded, distant or unclear head is uncertain. A missing-helmet goal with no clear uncovered head has detected_target=false and goal_event=null; another evidenced active rule may still match a facility goal. An explicit wearing-helmet goal instead requires a visible worn helmet; do not invert it to missing-helmet detection. Periodic audits also inspect empty scenes for static hazards.
- When people are visible, give a detailed observable activity account in `scene_understanding`, even when no monitoring target matches. Distinguish people by location and visible clothing (for example, "the person in a blue shirt on the left"). Describe each person's posture, movement direction, visible hand actions, objects handled, and interaction with nearby people or equipment where the frames support those details. Explain what changes from earlier to later selected frames and cite those frame numbers in the prose. Say when a task or movement cannot be determined; a person merely standing near equipment does not establish that they are operating it. Include observable helmet status when relevant to the active policy. Preserve compliant and uncertain activity as well as matches in Markdown history. Text, speech, reflections and shadows alone do not qualify.
- Return `helmet_observations` for visible people as objects with `helmet_status` (`worn`, `not_worn`, or `uncertain`), `head_visible` (boolean), `evidence_frame` (1-based selected frame), and `visible_evidence` (a short description). `not_worn` requires a clearly visible uncovered head, not mere person presence. If the head is unclear or occluded, use `uncertain`. A missing-helmet `goal_event.evidence_frame` must name a `not_worn` observation with `head_visible=true`. Use an empty list when no person's helmet status can be inspected.
- For a confirmed match, return `goal_event` with 1-based `start_frame`, `end_frame`, and `evidence_frame` indices in the selected sequence. Choose a frame that visibly supports the match, within that interval. For no match return null. These indices bind the notification time and attached image; do not guess an unsampled onset.
- Report each detection with observable label, category, useful visible color, position in the scene, activity, and confidence.
- Keep uncertainty explicit and grounded in visible evidence.
- In `scene_understanding`, describe the visible activity and temporal changes independently of target matches. In `uncertainties`, state occlusion, sampling gaps, insufficient motion evidence and other limits.
- In `risk_predictions`, forecast only plausible near-term outcomes supported by visible physical conditions or sampled motion. Each forecast must include `risk`, `visible_evidence`, `time_horizon`, `confidence` (0 to 1), `severity` (low, medium or high), `recommended_review`, and `evidence_frames` (unique 1-based indices of the selected frames showing its basis). These are predictions, never events that already happened. Return at most two concise forecasts, prioritizing the strongest visible basis, or an empty list when no forecast is supported by a selected frame. Do not invent speeds, distances, identities or intent. An empty list does not certify safety.
- Prefer a short qualitative horizon such as "if the observed movement continues in the next few seconds" when exact timing cannot be established. Recommend human review, not autonomous physical action.
- Separate a clearly observed match, a possible match, and no visible match. For a possible match, name the visual ambiguity in `summary` or `detection_report` so the operator can decide whether to focus or continue watching.
- If the goal asks whether something newly appeared, compare frames in this batch only when they show a reliable before-and-after view. Otherwise describe the current frame and say that first appearance cannot be established.
- For a corridor or walkway blockage goal, inspect the visible travel path. Count equipment, carts, packages, debris, or people as a match only when they visibly obstruct that path; describe their location and how much of the path appears obstructed. If the view cannot show enough of the path to judge, report uncertainty rather than a clear or blocked verdict.

## Restrictions
- Ignore shadows, reflections, signage text, and static background clutter unless directly relevant to the active analysis goal. Stationary objects on the floor are relevant when the operator asks to find foreign objects, debris, or obstructions.
- Set detected_target and detection_count from evidence matching the active goal. Unrelated people or routine activity do not count as matches. If the requested object is absent or unclear, say so without inventing a finding.
- Do not infer identity, intent, or off-camera facts.

## Facility review outputs
When a facility policy is supplied, return `site_findings` for each configured rule
that you can examine. Each object requires `rule_id`, `status` (observed, possible,
not_observed), `confidence` (0..1), `visible_evidence` (max800 characters) and
`evidence_frames` (unique 1-based selected frame indices). Omit a rule you cannot
examine; omitted rules remain unexamined, never clear. Do not create unknown rule
IDs. Use possible for insufficient perspective, head visibility or motion.
For uncovered_head, supply same-frame `helmet_observations`; for observed approach
or crossing, cite at least two actual frames. Named zones are normalized full-view
rectangles supplied by the operator, not metric calibration or privacy masking.
Every risk prediction also requires `evidence_frames` in factory/hotel profiles.
Forecasts are hypotheses for human review, not incident counts or calibrated
probabilities. Do not infer identity, protected traits, emotion, intent, injury,
unauthorized access, required PPE, or a breach of law from appearance. Hotel scope
is approved public/common-area cameras only; never claim private-room coverage.
Empty or uncertain findings cannot certify safety. Do not invent site response
owners, deadlines, sensor measurements or actions that were performed.

## Return Format
Return only one complete, compact JSON object. Do not write reasoning, tags,
Markdown fences or any text outside the JSON. Include only these top-level keys:
detected_target, detections, confidence, summary, scene_understanding,
risk_predictions, uncertainties, goal_event, helmet_observations, site_findings.
Keep private reasoning out of the final JSON.

`summary` and `scene_understanding` must be plain-language strings, not lists or
objects. Put the observable activity and temporal changes in scene_understanding.
`uncertainties` must always be a JSON array of strings, even for one limitation:
use ["The person's hands are occluded."] rather than a bare string. Use [] when
there are no additional limitations to report. `risk_predictions`, `detections`,
`helmet_observations` and `site_findings` must also always be arrays. Risk severity
must be exactly one of the lowercase strings "low", "medium" or "high".
Each detection's label/category is at most 80 characters, color at most 60,
and position/activity at most 160 each. Keep the detailed scene account only in
scene_understanding. Do not repeat sentences within a field or across fields.
Do not repeat the scene in legacy fields such as detection_report,
activity_description, visible_subjects, detected_types or appearance_notes; the
report adapter supplies those fields from this compact account.
Keep `summary` to one short sentence. Use two to six concrete sentences for
`scene_understanding` when people are visible (at most 1800 characters), with
enough detail to explain their actions and temporal changes. A quiet scene may
need only one sentence. Keep other evidence descriptions brief; preserve frame
references and uncertainty instead of repeating the scene.
Keep the complete answer within approximately 900 output tokens. Prioritize the
person's observable activity and required frame references. Omit weak or
redundant forecasts rather than dropping evidence references or uncertainty.

Use these exact nested object fields:
- Each `site_findings` item: rule_id, status, confidence, visible_evidence, evidence_frames.
- Each `risk_predictions` item: risk, visible_evidence, time_horizon, confidence, severity, recommended_review, evidence_frames.
- Each `helmet_observations` item: helmet_status, head_visible, evidence_frame, visible_evidence.
- `goal_event`: null, or an object with start_frame, end_frame, evidence_frame.

All frame references must be integers from 1 through the supplied selected frame
count. `evidence_frames` must be a nonempty list of distinct valid indices. Never
leave a finding or prediction without its frame references. Omit an unsupported
finding or prediction instead of inventing evidence. Return empty lists when
appropriate; an omitted facility rule stays unexamined, never clear. Do not assume
that a warehouse requires PPE: report the visible head condition and leave site
policy and any response to the supervisor.
