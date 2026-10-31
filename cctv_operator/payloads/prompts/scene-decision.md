# Monitoring decision from frame evidence

## Targets
{target_description}

## Current analysis goal
{attention_instruction}

Evaluate this requested observable condition from the supplied current Cosmos
frame descriptions. You do not see the images. `detected_target` answers whether
the requested condition is observed, including a negative condition. It does not
answer whether a law or site policy has been breached. A request to find someone
without a safety helmet can match a clearly visible uncovered head even when the
site has no mandatory PPE rule. A request to find someone wearing a safety helmet
requires a visible worn helmet. Preserve arbitrary goals and their negation;
never replace them with the default helmet goal or a facility rule.

If the requested condition is supported, set detected_target=true and goal_event
to its actual supporting frame interval and evidence_frame. If it is absent or
uncertain, set detected_target=false and goal_event=null. Confidence describes
support from the actual current evidence. Do not copy a historical decision.

Describe the current scene and supported changes in two to six concise sentences
in scene_understanding, even when the goal does not match. Use one detection per
visibly distinguishable subject; a continuing appearance is not another person.
Do not infer identity, intent, injury, exact speed/distance, or continuous coverage.
A single image cannot establish motion. Motion and before/after claims require
at least two current frame descriptions explicitly supporting a change.

For relevant headwear, a cloth cap is not a safety helmet. An occluded, distant or unclear head is uncertain.
Use helmet_status=not_worn only with a clearly visible head and explicit evidence
that no safety helmet is worn. That same helmet_observation must have
head_visible=true. An unclear head requires uncertain, never not_worn or worn.
Bind every helmet observation to the described frame. A missing-helmet goal match
must cite a not_worn/head_visible=true observation on goal_event.evidence_frame.

Evaluate only supplied facility rules, independently of the active goal. An
observed uncovered_head finding needs same-frame not_worn/head_visible=true
helmet evidence. Otherwise mark it possible or omit it. Motion/proximity rules
need at least two supporting current frames. group_presence requires at least
two real people together in the same frame; one person repeated across frames
is not a group. Use possible for uncertain evidence and not_observed only when
a clear view establishes absence. Omitted rules stay unexamined, never clear.

Return at most two physical risk predictions with supporting evidence_frames,
qualitative time horizon, confidence, lowercase severity and a human review action.
A current missing helmet is an observation, not a future risk. Unsupported
forecasts should be empty. Forecasts and empty lists never certify safety.

Return one complete compact JSON object matching the strict schema. Include all
ten required fields. Keep summary at most160 characters, scene_understanding at
most1800, detection label/category/color/position/activity at most80/80/60/160/160,
helmet evidence at most160 and facility evidence at most200 characters. Preserve
lists, uncertainty, configured rule IDs and original selected-frame indices.
Never invent evidence references or use historical text as a current frame.
