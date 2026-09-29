# Runtime and deployment topology

**Section:** 02 · Inferred system architecture  
**Specification ID:** `AR-02-03`  
**Customer question:** What runs where, and how do deployment and operational boundaries differ from source structure?

## What to include

- Identify processes, workers, scheduled jobs, queues, stores, and external endpoints for each reviewed environment.
- Show placement, replicas, network boundaries, deployment units, and shared infrastructure when supported by evidence.
- Explain startup order, configuration dependencies, and important operational control paths.
- Distinguish intended configuration from observed production topology and record environment-specific differences.

## Why this matters

Reliability, scaling, and rollout decisions depend on runtime topology rather than only on imports. This view prevents advice based on a development configuration from being presented as production architecture.

## Evidence to use

Use deployment manifests, infrastructure definitions, process launchers, environment configuration, and authorized runtime inventory or telemetry. Redact secrets and sensitive endpoint details.

## Expected report output

An environment-labeled topology view plus a runtime inventory containing unit, placement, replica information, interfaces, stores, and evidence status.

## Completion and quality checks

Do not infer active replica counts or failover behavior from example manifests. State the observation date and whether deployment state was directly verified.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
