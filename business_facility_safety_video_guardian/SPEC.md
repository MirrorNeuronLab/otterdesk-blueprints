# Facility Safety Video Guardian SPEC

## What We Want To Achieve

Build a reviewable safety-monitoring workflow that reduces manual video watching while still giving operations teams enough evidence to trust each escalation. The target customer should be able to see what was observed, why an alert was or was not sent, and how to tune the workflow for their facility.

## Customer Problem

Facilities, security, safety operations, and property management teams need to watch continuous video streams without turning every frame into manual review. The real gap is not just detecting a visible face once; it is deciding when an observation is safety-relevant, avoiding duplicate alerts, and leaving enough evidence for a human team to trust what happened.

## Design Details

The blueprint is organized as a streaming safety loop. `ingress` starts the monitor, `door_camera_tick_source` emits frame ticks, and `person_detector` samples the configured video source, runs human detection with observable appearance and activity description, applies confidence and cooldown policy, and emits structured events only when a human is visible.

The prototype supports live VL model detection through an Ollama-compatible endpoint and deterministic mock detection for tests. When a face is visible, the model is asked to describe only non-identifying visible details such as face position, expression, hair/facial hair if visible, glasses, mask/hat, lighting, occlusion, and notable visible facial features. It must not identify the person or infer sensitive/private traits. Alert delivery is optional, with Slack-style payloads used as the reference integration. The design goal is to preserve the same input and output shape when replacing the local webcam stream with real camera streams.

## Input

The prototype accepts a configurable live camera source. By default, it expects a local RTSP stream carrying H.264 video at `rtsp://host.docker.internal:8554/local-camera`; local runs should publish the Mac webcam through the bundled MediaMTX helper. The key runtime controls are the source URI, transport, codec, frame sampling interval, maximum frame width, human detection confidence threshold, alert cooldown window, and site-specific safety or escalation policy.

Notification inputs include Slack enablement, destination channel, message prefix, and any downstream alert routing that a deployment wants to replace Slack with later. Model inputs include the VL model base URL, VL model name, prompt behavior, temperature, timeout, and mock or quick-test mode for deterministic local evaluation. The default VL model location is `http://192.168.4.173:11434` with model `nemotron3:33b`, and deployments can override it through config, generator flags, or `VL_MODEL_BASE_URL` / `VL_MODEL_NAME`.

Third-party apps may edit or replace `config/overwrite.json` before launch to override only the video source and VL model sections. Runtime should resolve `config/default.json` first, then deep-merge `config/overwrite.json` when present, leaving `default.json` as the canonical full baseline config.

For production use, the same contract should be fed by real camera streams, facility metadata, restricted-area definitions, operating hours, incident categories, and customer-specific escalation rules.

## Output: Expected Customer Outcome

The expected customer outcome is reduced manual monitoring burden while meaningful safety observations are escalated with enough context to review. A useful run produces explainable human detection events, observable appearance and activity descriptions, alert or no-alert decisions, cooldown-aware notification payloads, and operational evidence showing why the system did or did not escalate.

The result should help a safety team answer: what was seen, what visible appearance and activity details were observed, when it was seen, how confident the system was, whether an alert was sent, whether an alert was suppressed by policy or cooldown, and what a reviewer should inspect next.

## Evaluation Criteria

- Detection quality: measure human-detection precision, recall, false-alert rate, and missed-face rate against labeled clips or sampled frames.
- Alert usefulness: verify that alerts contain enough context for a human to decide whether action is needed.
- Alert latency: measure time from sampled frame to emitted notification and compare with customer response expectations.
- Cooldown correctness: confirm repeated detections do not create alert noise during the configured cooldown window.
- Policy fit: check whether alerts match site rules such as restricted-area presence, after-hours activity, or doorway monitoring.
- Auditability: confirm every alert can be traced to detection metadata, sampled frame timing, model result, and notification payload.
- Production readiness: evaluate real-camera reliability, model fallback behavior, privacy handling, and integration with the customer's incident workflow.

## Result Artifacts To Inspect

Inspect runtime events and worker logs for frame sampling, detection decisions, errors, and notification attempts. Review the final artifact or result payload for detection events, alert decisions, cooldown state, and notification details.

When run through the standard local run store, inspect `run.json`, `config.json`, `inputs.json`, `events.jsonl`, `result.json`, and `final_artifact.json`. For bundle-style review, also inspect the generated bundle summary and any specialized payload outputs.

## Prototype Limits

The current blueprint is an early prototype with webcam or synthetic test inputs, simplified alert policy, and optional mock detection for repeatable local runs. It is decision support for evaluation, not a certified safety system.

Real deployment still needs camera adapter hardening, privacy review, retention policy, customer-specific thresholds, incident-response integration, and validation against representative facility footage.

## Upgrade Path To Real Customer Use

Replace the local webcam source with a customer camera adapter while preserving the same input shape. Calibrate thresholds and cooldowns using labeled customer clips. Add customer policy rules for site layout, operating hours, restricted zones, and incident severity.

Connect alerts to the customer's existing security, ticketing, or incident-response system. Track detection quality, alert noise, latency, reviewer acceptance, and missed-event analysis over time so the system improves against real operating outcomes.
