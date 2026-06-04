# Video Watch Assistant SPEC

## What We Want To Achieve

Build a reviewable video monitoring workflow that reduces manual video watching while giving operations teams enough evidence to trust each visual-detection escalation. The customer should be able to see what was observed, how many targets were detected, what label/category/color each item appeared to be, why an alert was or was not sent, and how to tune the workflow for the site.

## Customer Problem

Video operators and critical-infrastructure security teams need to watch continuous video without turning every frame into manual review. The real gap is not just seeing something once; it is deciding when configured subjects or activities matter, avoiding duplicate alerts, and leaving enough evidence for reviewers to trust what happened.

## Design Details

The blueprint is organized as a streaming visual-detection loop. `ingress` starts the monitor, `video_frame_tick_source` emits frame ticks, and `visual_detector` samples the configured video source, runs visual detection, reports count/label/category/color/position/activity details, applies confidence and cooldown policy, and emits structured events when configured targets appear in the monitored scene. It also maintains conversation context so OtterDesk local AI can answer what happened from live observations, accepts operator attention requests, and emits chat-facing `human_notice` events when a significant change should be surfaced promptly.

The OtterDesk local chat model uses `prompts/chat-system.md` as this blueprint's co-worker system prompt. The prompt makes the model speak as Video Watch Assistant, answer job-related questions from runtime observations and human-in-the-loop events, explain detection or alert decisions, and say clearly when evidence is missing or operator input is needed.

The prototype supports live VL model detection through Docker Model Runner on an NVIDIA-accelerated runtime node and deterministic mock detection for tests. The model is asked to count only real visible subjects or activity relevant to the configured targets, and to ignore shadows, reflections, signage text, static background clutter, and uncertain guesses. Alert delivery is optional, with Slack-style payloads used as the reference integration.

## Input

The prototype accepts a mapped local RTSP source through a host-side mapper started by the standard `scripts/pre-launch.sh` hook and cleaned by `scripts/post-launch.sh`. By default, the mapper loops `data/sample.mp4` into `rtsp://127.0.0.1:8554/video-watch`; if that port is busy, it selects another local port and reports the resolved URI back to the runner before validation and submission. On stop, cancel, failed launch, terminal completion, or stale run cleanup, the post-launch hook stops the recorded ffmpeg/MediaMTX mapper and matching MediaMTX listeners on the selected preview ports. The key runtime controls are the mapped source URI, transport, codec, frame sampling interval, maximum frame width, detection confidence threshold, alert cooldown window, target prompt, and site-specific escalation policy.

Notification inputs include Slack enablement, destination channel, message prefix, and any downstream alert routing that a deployment wants to replace Slack with later. Model selection is built into the blueprint as `otterdesk-video-watch:default`; users do not set a model URL or model name. Live runs require a DGX Spark, GH200, H100, H200, B200, or GB200 class NVIDIA node with Docker Model Runner acceleration.

Third-party apps may edit or replace `config/overwrite.json` before launch to override the video source section. Runtime should resolve `config/default.json` first, then deep-merge `config/overwrite.json` when present, leaving `default.json` as the canonical full baseline config.

For production use, the same contract should be fed by real video stream streams, site metadata, monitored-zone definitions, operating hours, incident categories, and customer-specific escalation rules.

## Output: Expected Customer Outcome

The expected customer outcome is reduced manual monitoring burden while meaningful visual observations are escalated with enough context to review. A useful run produces explainable frame observations, detection events, count/label/category/color/position/activity details, chat-facing human notices for major changes, alert or no-alert decisions, cooldown-aware notification payloads, and operational evidence showing why the system did or did not escalate.

The result should help a safety or security team answer: what configured targets were seen, how many were detected, what visible labels/categories/colors were observed, where and when they were seen, how confident the system was, whether the co-worker notified the user in chat, whether an alert was sent, whether an alert was suppressed by policy or cooldown, and what a reviewer should inspect next.

The live review surface is declared as Grafana-style dashboard JSON under `web_ui.dashboard.grafana` and rendered by the shared blueprint support Gradio service. The video-specific behavior lives in panel declarations and event targets, not in custom dashboard HTML.

## Evaluation Criteria

- Detection quality: measure precision, recall, false-alert rate, and missed-detection rate against labeled clips or sampled frames.
- Detail quality: verify that alerts include useful count, label, category, color, position, and activity details.
- Alert latency: measure time from sampled frame to emitted notification and compare with customer response expectations.
- Cooldown correctness: confirm repeated detections do not create alert noise during the configured cooldown window.
- Policy fit: check whether alerts match site rules such as restricted access, after-hours activity, monitored-area movement, or other configured targets.
- Auditability: confirm every alert can be traced to detection metadata, sampled frame timing, model result, and notification payload.
- Production readiness: evaluate real-camera reliability, model fallback behavior, retention policy, and integration with the customer's incident workflow.

## Result Artifacts To Inspect

Inspect runtime events and worker logs for frame sampling, detection decisions, errors, and notification attempts. Review the final artifact or result payload for visual detection events, alert decisions, cooldown state, and notification details.

When run through the standard local run store, inspect `run.json`, `config.json`, `inputs.json`, `events.jsonl`, `result.json`, and `final_artifact.json`. For bundle-style review, also inspect the generated bundle summary and any specialized payload outputs.

## Prototype Limits

The current blueprint is an early prototype with RTSP or synthetic test inputs, simplified alert policy, and optional mock detection for repeatable local runs. It is decision support for evaluation, not a certified safety or security system.

Real deployment still needs camera adapter hardening, privacy review, retention policy, customer-specific thresholds, incident-response integration, and validation against representative video footage.

## Upgrade Path To Real Customer Use

Calibrate thresholds and prompts using labeled customer clips. Add customer policy rules for site layout, operating hours, restricted zones, entry direction, and incident severity.

Connect alerts to the customer's existing security, ticketing, or incident-response system. Track detection quality, alert noise, latency, reviewer acceptance, and missed-event analysis over time so the system improves against real operating outcomes.
