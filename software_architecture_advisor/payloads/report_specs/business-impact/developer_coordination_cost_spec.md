# Developer coordination cost

**Section:** 20 · Business impact  
**Specification ID:** `AR-20-04`  
**Customer question:** Which architectural dependencies create avoidable coordination work?

## What to include

- Identify change scenarios requiring multi-team reviews, synchronized releases, repeated handoffs, or shared subsystem decisions.
- Separate necessary domain collaboration from coordination imposed by implementation boundaries.
- Quantify time or cost only from supplied measurements or explicit, reviewable assumptions.
- Describe how a proposed boundary or ownership change would alter the coordination process.

## Why this matters

Customers can evaluate architecture investment more concretely when the coordination mechanism is visible. The goal is to remove unnecessary dependencies, not to imply that collaboration itself is waste.

## Evidence to use

Use cross-team change analysis, ownership, review and release timestamps, representative work histories, and stakeholder-confirmed effort assumptions.

## Expected report output

A coordination-cost model with change class, participants by role, handoffs, measured or assumed effort, architectural cause, and proposed reduction.

## Completion and quality checks

Do not equate elapsed waiting with paid labor or infer individual productivity. Avoid double counting the same delay in lead-time, effort, and cost summaries.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
