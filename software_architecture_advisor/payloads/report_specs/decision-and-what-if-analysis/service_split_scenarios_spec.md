# Service split scenarios

**Section:** 16 · Decision and what-if analysis  
**Specification ID:** `AR-16-01`  
**Customer question:** What would happen if this service were split along a proposed seam?

## What to include

- Define the proposed responsibility split and the baseline architecture being changed.
- Map new contracts, data ownership, deployment units, and operational responsibilities.
- Assess transaction, consistency, latency, reliability, testing, and coordination consequences.
- Compare keeping the service together, splitting internally, and creating separate runtime services.

## Why this matters

Customers need to know whether a split creates meaningful independence or merely distributes existing complexity. A scenario comparison makes the intended benefit and the new obligations visible before implementation.

## Evidence to use

Use responsibility maps, typed dependencies, workflow traces, state ownership, release history, and supplied requirements.

## Expected report output

A split decision brief with before/after boundaries, expected benefits, new costs, blockers, staged experiment, and decision criteria.

## Completion and quality checks

Do not assume a network boundary improves modularity. Label proposed behavior as hypothetical and identify the evidence needed to test claims about independent deployment or scaling.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
