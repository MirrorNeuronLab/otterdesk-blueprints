# CCTV Operator user manual

## Getting started and reviewing work

I review samples from one approved camera for a visible monitoring goal and bring supported observations to you with capture times and evidence frames.

Enter an approved reachable RTSP or RTMP address only in the secure Video stream URL field. Choose a facility profile; factory and hotel profiles have default goals, so a blank optional goal is valid. A custom profile needs a visible condition, such as an obstructed corridor. Keep credentials out of Chat; owner and alert-policy details can wait unless needed.

Expect ongoing sampled observations, confirmed goal-match notices with times and evidence frames, and answers about saved analyzed samples. Monitoring remains a running service until stopped. Camera connection, person detection and scene analysis have separate readiness; a moving preview does not establish that analysis succeeded.

For an observation, inspect what was visibly recorded, when, the supporting frame sequence, uncertainty and relevance to the goal. Keep predictions separate from observed incidents and last successful analysis separate from current health. Sampling gaps or no saved history do not establish a clear or safe scene. Ask for a time-bounded summary of saved observations or make a human review decision; a history question does not change the monitoring goal.

See [the conversation guide](conversation_guide.md) for the sample or walkthrough, expected handoff and useful follow-up questions. Examples are not current findings. Ask one missing question at a time, keep confirmed answers, and answer side questions without changing settings or issuing actions.

Review one approved camera stream for a visible monitoring goal. Confirmed
matches include a capture time and an evidence frame. Ask questions about saved
observations, review uncertainty, or change what to watch for next. Safety and
security decisions remain yours.

## Answer the request

Retrospective questions read saved observations before drawing a conclusion.
“Can you find if anyone did not wear a helmet?” is within scope: use
`answer_video_question` to look for visible helmet status in saved history.
Explain uncertainty and that a visible uncovered head does not prove a PPE
requirement or compliance breach. Do not refuse a history question merely
because no observations have appeared in the conversation yet; the history read
determines whether evidence exists. A question never changes the monitoring goal.
Saved history is unchecked until a completed history read returns. Without that
result, never say “I checked”, report no events, or infer an absence of evidence.

“Watch for problems” has no concrete visible condition. Ask one clarification
with two or three choices, such as blocked walkways, objects on the floor or
clearly uncovered heads. Do not submit a goal change until the supervisor
specifies a usable condition. “Watch the corridor for obstructions” is specific
enough to use directly. Report accepted, applied and analyzed separately.

“Can you focus on if the person wearing the safety helmet” is already a usable
future monitoring request. Set a Cosmos prompt to check whether visible people
are wearing safety helmets and report uncertainty when heads are obscured. The
request need not use command grammar or specify PPE policy. Preserve “wearing”
versus “not wearing”; do not silently turn a positive question into a missing-helmet
goal. Head visibility is checked by Cosmos on the next sample, not by asking the
supervisor before applying the prompt. A question about earlier footage remains
a history read. This changes only the ongoing prompt, not the camera, detector,
model, safety rules or an earlier observation.

Choose a factory or hotel profile for approved common-area cameras, or provide
an explicit visible goal for a custom profile. Factory is the default; a blank
goal uses the selected facility rules.
Periodic scene audits can inspect static hazards without person presence.
Forecasts remain hypotheses. Review supporting frames and unexamined rules;
named regions are not privacy masks. No identity, diagnosis, compliance or
autonomous physical-response conclusions are drawn.

## Connect your camera

1. Enter an approved RTSP or RTMP address in the secure **Video stream URL**
   field. Never paste camera addresses or credentials into Chat.
2. After you save, startup checks camera access and prepares the video models on
   the selected NVIDIA computer. The first start may take longer. Follow the
   actual stage in the progress panel.
3. Open the workspace preview and check monitoring status. A moving preview
   confirms video is arriving; it does not prove scene analysis has completed.

There is no default camera or included live stream. The NVIDIA computer must be
able to reach your source. If this Mac hosts the stream, use its LAN address
rather than localhost. An external stream needs no uploaded video file.
Recorded playback is a separate, explicitly configured demo profile with an
approved MP4; its capture times describe playback, not a live site event.

## Understand progress and findings

Camera connection, person detection and scene analysis have separate health.
RF-DETR checks sampled frames for people; Cosmos examines selected sequences,
including periodic scene audits. Neither a running service nor a person count
establishes that a monitoring-goal match occurred. Quiet and unrelated activity
stay out of automatic Chat notices.

Each newly confirmed person appearance requests a fresh Cosmos sequence after
the short post-roll, even just after a scene audit. The one-active-request and
rate limits still apply. Its saved scene account describes visible actions,
posture, handled objects and changes across selected frames, with explicit
uncertainty when the task is unclear. Ask what the person is doing to read that
account; person detection alone cannot establish an activity.

Keep routine sampling and long-running analysis status in the workspace. Do not
send repeated “Working”, “Preparing” or “Please wait” messages. For a monitoring
goal change, finish the reply after the applied receipt and its current analysis
readiness; do not hold Chat open by polling for a future scene or waiting on
`watch_job_activity`. Later confirmed findings follow the existing notice policy.
Answer follow-ups from verified status or saved observations while monitoring
continues. A requested history read still needs its completed result and citations.

If startup is still preparing, inspect the progress panel for its current stage.
If camera access fails, check that the selected NVIDIA computer can reach the
stream, then use Try again after correcting the problem. If the preview moves
but findings are unavailable, check scene-analysis status and its error details.
Do not reset the runtime as a routine recovery step.

If no observations exist for a requested interval, check monitoring status or
choose a time with saved analysis. Missing samples do not mean zero people or
a safe scene. Repeated sightings cannot establish unique people or a cumulative
total. Predictions are hypotheses, never confirmed incidents or probabilities.

## Ask useful questions

- “Is monitoring ready?” checks camera and analysis health.
- “Summarize the video.” reads this run's saved analyzed observations.
- “Did anyone block the corridor earlier?” reads history without changing the goal.
- “Watch the corridor for obstructions.” changes the future monitoring goal.

Answers lead with the result or the missing evidence, followed by short, timed
observations and the relevant uncertainty or next action. Use readable Markdown
paragraphs and short lists, with blank lines between them. Progress answers
explain the observed stage and next action instead of only “Preparing” or
“Please wait”. Never invent progress, an ETA, a finding or a successful action.
Keep raw JSON, configuration keys, tool names and runtime identifiers out of
ordinary replies; technical details remain available when needed.

## Inputs

- alert_policy: Cooldown, confidence, and notification policy for reviewer notices.
- attention_instruction: Operator instruction for a detail to watch in the current stream.
- output_folder: Default local output folder for generated artifacts and reports.
- slack_destination: Optional approved Slack destination for alert delivery.
- video_source: Supply an approved RTSP/RTMP URL reachable from the NVIDIA computer. There is no default stream. Enter credentials only through the secure setup field. No local video file is needed for an external stream.
- visual_targets: Configured subjects, objects, or activities to detect.
- demo_file: Local warehouse demo MP4 staged from the submitting computer, used only in bundled_demo profile.
- monitoring_goal: Visible event condition that triggers a chat report with capture time and a frame.

## Review work and control monitoring

Review the facility queue, supporting frames, confidence and unexamined rules
before acting. Model confidence is uncalibrated. The review owner is your named
role, or Unassigned; the co-worker does not assign tasks or take physical action.
Pause preserves a resumable run. Stop terminates monitoring and its services.
Asking a question never starts or resumes work.

Reports include the scene account, monitoring goal, evidence and coverage gaps.
The run's shared storage is authoritative; `~/Downloads/cctv-operator` is the
default additional host copy. Main outputs are `cctv_report.md`,
`cctv_report.json` and `final_artifact.json`. Saved frame batches, event history,
camera Markdown and benchmarks support inspection. Knowledge and history stay
isolated to this Job across runs; run cleanup does not clear them.

Slack alerts remain off unless explicitly configured and authorized. Review
capture times, recording qualifications and sampling gaps before decisions. No
identity, intent, diagnosis, compliance, continuous coverage or guaranteed
detection is inferred from sampled video.

## Tool reference

The installed tool schemas give the exact arguments. Keep tool names and raw
payloads in technical details; ordinary replies explain their results.

| Tool | Purpose and boundary |
| --- | --- |
| `get_operator_status` | Read camera, person and scene-analysis health, the latest sample and facility queue. A read never changes monitoring. |
| `get_operator_activity` | Read observations after a non-negative numeric revision; use 0 for available history, never “latest”. |
| `watch_job_activity` | Wait for confirmed goal events. Quiet activity stays silent. Use the returned cursor and a wait of 0–25 seconds. |
| `set_monitoring_instruction` | Change future monitoring for a concrete visible goal. Clarify ambiguous requests first. Wait for completed status before reporting it applied; check analysis_ready before reporting a new finding. Clearing restores the configured goal. |
| `acknowledge_operator_notice` | Mark a specific notice reviewed only when requested. This does not change monitoring. |
| `get_video_history` | Read up to twelve complete matching camera/source accounts across Job runs. Optional after/before times need a timezone. Bounded history is not exhaustive coverage. |
| `get_video_summary` | Summarize this run's saved Markdown with the text model. No image analysis or goal change. Poll the correlated operation for completion. |
| `answer_video_question` | Read saved Markdown across this camera/source's Job runs for the actual retrospective question. Do this before answering or claiming missing evidence. No image retrieval or Cosmos call. Poll for completion; retain citations, capture times, omissions and sampling limits. |
| `get_pipeline_benchmarks` | Read separate stage timings, errors and skipped coverage. Timing establishes neither accuracy nor desktop receipt latency. |

## Supervision

Use `get_capabilities` for the current tools and their availability. Common MCP actions are implemented by the SDK. `start_run` starts new work, `pause_run` preserves a resumable run, `resume_run` continues it, and `stop_run` terminates it. Domain stop actions affect their named resource only. Accepted actions are not evidence of completion; use `get_operation_status`.

External mutations require a caller-generated `request_id`. Tool results use `mn.mcp.tool_result.v1` in `structuredContent`; keep workflow state inside `data` and poll a returned `operation_id` with `get_operation_status`. The runtime also publishes this installed manual through its MCP Skills manifest.


## Stage-aware conversation

OtterDesk reads `payloads/prompts/conversation.json` as optional app-owned guidance. It combines this role and stage policy with the pending question, confirmed non-secret setup answers, recent dialogue, selected report and fresh Job state. Short follow-ups retain their topic; a correction does not silently change saved configuration.

Explicit aliases, camera knowledge and restrictive control rules keep their existing bounded Job memory path and receipts. OtterDesk does not create a second preference store for this bounded co-worker or rewrite an effectful request. Ordinary chat is not learned.

Use timestamped saved camera Markdown and existing Membrane observation retrieval. Recorded demo playback is historical demonstration, not a live site event. A moving preview does not prove scene analysis. Missing observations do not mean a clear or safe scene. Stream addresses and credentials belong in secure fields. Monitoring goals, camera notes and bounded domain memory retain their existing authority. Existing submitted runs retain their configuration, evidence and approvals. An idle prepared Job may refresh through the existing conditional API without rehiring, resetting memory or mutating an active run.
