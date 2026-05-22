# Video Watch Assistant SPEC

## What We Want To Achieve

Build a reviewable video monitoring workflow that reduces manual video watching while giving operations teams enough evidence to trust each visual-detection escalation. The customer should be able to see what was observed, how many targets were detected, what label/category/color each item appeared to be, why an alert was or was not sent, and how to tune the workflow for the site.

## Customer Problem

Video operators and critical-infrastructure security teams need to watch continuous video without turning every frame into manual review. The real gap is not just seeing something once; it is deciding when configured subjects or activities matter, avoiding duplicate alerts, and leaving enough evidence for reviewers to trust what happened.

## Design Details

The blueprint is organized as a streaming visual-detection loop. `ingress` starts the monitor, `video_frame_tick_source` emits frame ticks, and `visual_detector` samples the configured video source, runs visual detection, reports count/label/category/color/position/activity details, applies confidence and cooldown policy, and emits structured events when configured targets appear in the monitored scene.

The prototype supports live VL model detection through an Ollama-compatible endpoint and deterministic mock detection for tests. The model is asked to count only real visible subjects or activity relevant to the configured targets, and to ignore shadows, reflections, signage text, static background clutter, and uncertain guesses. Alert delivery is optional, with Slack-style payloads used as the reference integration.

## Input

The prototype accepts a configurable live camera source through a host-side mapper started by the standard `scripts/pre-launch.sh` hook. By default, the mapper loops `data/sample.mp4` into the stable RTSP endpoint `rtsp://127.0.0.1:8554/video-watch`; when a user supplies an RTSP URL, the mapper validates it outside OpenShell and republishes it into that same endpoint. The key runtime controls are the mapped source URI, optional upstream URI, transport, codec, frame sampling interval, maximum frame width, detection confidence threshold, alert cooldown window, target prompt, and site-specific escalation policy.

Notification inputs include Slack enablement, destination channel, message prefix, and any downstream alert routing that a deployment wants to replace Slack with later. Model inputs include the VL model base URL, VL model name, prompt behavior, temperature, timeout, and mock or quick-test mode for deterministic local evaluation. The default VL model location is `http://192.168.4.173:11434` with model `nemotron3:33b`, and deployments can override it through config, generator flags, or `VL_MODEL_BASE_URL` / `VL_MODEL_NAME`.

Third-party apps may edit or replace `config/overwrite.json` before launch to override only the video source and VL model sections. Runtime should resolve `config/default.json` first, then deep-merge `config/overwrite.json` when present, leaving `default.json` as the canonical full baseline config.

For production use, the same contract should be fed by real video stream streams, site metadata, monitored-zone definitions, operating hours, incident categories, and customer-specific escalation rules.

## Output: Expected Customer Outcome

The expected customer outcome is reduced manual monitoring burden while meaningful visual observations are escalated with enough context to review. A useful run produces explainable detection events, count/label/category/color/position/activity details, alert or no-alert decisions, cooldown-aware notification payloads, and operational evidence showing why the system did or did not escalate.

The result should help a safety or security team answer: what configured targets were seen, how many were detected, what visible labels/categories/colors were observed, where and when they were seen, how confident the system was, whether an alert was sent, whether an alert was suppressed by policy or cooldown, and what a reviewer should inspect next.

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
