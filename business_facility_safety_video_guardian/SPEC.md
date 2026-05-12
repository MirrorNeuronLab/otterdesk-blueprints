# Facility Safety Video Guardian SPEC

## What We Want To Achieve

Build a reviewable safety-monitoring workflow that reduces manual video watching while still giving operations teams enough evidence to trust each escalation. The target customer should be able to see what was observed, why an alert was or was not sent, and how to tune the workflow for their facility.

## Customer Problem

Facilities, security, safety operations, and property management teams need to watch continuous video streams without turning every frame into manual review. The real gap is not just detecting a person once; it is deciding when an observation is safety-relevant, avoiding duplicate alerts, and leaving enough evidence for a human team to trust what happened.

## Design Details

The blueprint is organized as a streaming safety loop. `ingress` starts the monitor, `door_camera_tick_source` emits frame ticks, and `person_detector` samples the configured video source, runs detection, applies confidence and cooldown policy, and emits structured events.

The prototype supports live Ollama/VLM detection and deterministic mock detection for tests. Alert delivery is optional, with Slack-style payloads used as the reference integration. The design goal is to preserve the same input and output shape when replacing the sample video with real camera streams.

## Input

The prototype accepts a camera or video source, currently represented by a bundled sample video or image-compatible source. The key runtime controls are the frame sampling interval, maximum frame width, person detection confidence threshold, alert cooldown window, and site-specific safety or escalation policy.

Notification inputs include Slack enablement, destination channel, message prefix, and any downstream alert routing that a deployment wants to replace Slack with later. Model inputs include the Ollama base URL, VLM model name, prompt behavior, temperature, timeout, and mock or quick-test mode for deterministic local evaluation.

For production use, the same contract should be fed by real camera streams, facility metadata, restricted-area definitions, operating hours, incident categories, and customer-specific escalation rules.

## Output: Expected Customer Outcome

The expected customer outcome is reduced manual monitoring burden while meaningful safety observations are escalated with enough context to review. A useful run produces explainable detection events, alert or no-alert decisions, cooldown-aware notification payloads, and operational evidence showing why the system did or did not escalate.

The result should help a safety team answer: what was seen, when it was seen, how confident the system was, whether an alert was sent, whether an alert was suppressed by policy or cooldown, and what a reviewer should inspect next.

## Evaluation Criteria

- Detection quality: measure person-detection precision, recall, false-alert rate, and missed-person rate against labeled clips or sampled frames.
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

The current blueprint is an early prototype with bundled or synthetic inputs, simplified alert policy, and optional mock detection for repeatable local runs. It is decision support for evaluation, not a certified safety system.

Real deployment still needs camera adapter hardening, privacy review, retention policy, customer-specific thresholds, incident-response integration, and validation against representative facility footage.

## Upgrade Path To Real Customer Use

Replace the sample video source with a customer camera adapter while preserving the same input shape. Calibrate thresholds and cooldowns using labeled customer clips. Add customer policy rules for site layout, operating hours, restricted zones, and incident severity.

Connect alerts to the customer's existing security, ticketing, or incident-response system. Track detection quality, alert noise, latency, reviewer acceptance, and missed-event analysis over time so the system improves against real operating outcomes.
