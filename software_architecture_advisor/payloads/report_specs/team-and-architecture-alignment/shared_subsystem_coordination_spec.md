# Shared subsystem coordination

**Section:** 15 · Team and architecture alignment  
**Specification ID:** `AR-15-05`  
**Customer question:** Where do several teams repeatedly contend for the same architectural decision or release?

## What to include

- Identify shared subsystems with repeated multi-team changes, review queues, or conflicting priorities.
- Explain the common responsibility, interface, or state that creates the coordination requirement.
- Assess whether a platform ownership model, clearer contract, internal decomposition, or retained collaboration fits the need.
- Define how a proposed change would reduce unnecessary coordination without hiding shared obligations.

## Why this matters

A shared subsystem can become an organizational bottleneck even when its code is technically sound. Customers need a practical ownership and interface decision rather than a blanket recommendation to decentralize.

## Evidence to use

Use cross-team change findings, ownership records, release dependencies, review flows, and stakeholder-confirmed examples.

## Expected report output

A shared-subsystem decision brief with participating teams or roles, coordination mechanism, impact evidence, options, and success measure.

## Completion and quality checks

Do not attribute delay to individual teams without evidence or assume that adding service boundaries removes collaboration. Keep legitimate shared business decisions visible.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
