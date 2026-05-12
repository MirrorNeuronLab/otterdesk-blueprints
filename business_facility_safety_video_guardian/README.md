# Facility Safety Video Guardian

`Blueprint ID:` `business_facility_safety_video_guardian`  
`Category:` business - Business Solution Template  
`Default LLM:` Ollama `nemotron3:33b` with deterministic fake LLM support for tests

## Intro

Facility Safety Video Guardian is an early MirrorNeuron blueprint for monitoring facility video streams and escalating safety-relevant observations. It demonstrates how an agent can watch sampled video state, reason over whether a person is visible, apply alert cooldown logic, and produce reviewable notification payloads.

This README is the short product introduction. The detailed design contract, expected customer outcome, inputs, outputs, and evaluation criteria live in [SPEC.md](SPEC.md).

## Who It Serves

This blueprint is for facilities, security, safety operations, and property management teams that need help reducing manual monitoring burden without losing reviewability.

## What It Demonstrates

- Video stream sampling for a door or facility camera.
- Person detection through a VLM/Ollama path or deterministic mock mode.
- Cooldown-aware alert decisions to avoid notification noise.
- Structured events and artifacts that a human reviewer can audit.

## Example Scenario

A front-door camera is sampled every few seconds. The agent checks whether a person is visible, decides whether the event is alert-worthy, suppresses duplicates during cooldown, and emits an alert payload for review or Slack delivery.

## Quick Start

Generate a quick deterministic bundle for local review:

```bash
cd business_facility_safety_video_guardian
python3 generate_bundle.py --quick-test --output-dir /tmp/mirror-neuron-bundles
```

Then run the generated bundle with the MirrorNeuron runtime entrypoint.

## Documentation Map

- [SPEC.md](SPEC.md): design details, desired customer outcome, input/output contract, evaluation criteria, prototype limits, and upgrade path.
- `manifest.json`: runtime graph, nodes, edges, initial inputs, and metadata.
- `config/default.json`: default identity, inputs, LLM, output, logging, and adapter settings.
- `payloads/`: bundled worker code, demo media, and supporting runtime assets.

## Prototype Status

This blueprint is a working prototype with mock-friendly execution paths. It is intended for product evaluation and customer discovery before connecting real cameras, incident workflows, and production safety policies.
