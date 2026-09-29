# Boundary deterioration

**Section:** 14 · Architecture evolution  
**Specification ID:** `AR-14-03`  
**Customer question:** Which previously useful boundaries are losing their intended separation?

## What to include

- Identify the original boundary purpose and the baseline evidence that it was enforced or respected.
- Track new internal access, shared state, cross-layer edges, or coordinated releases across that boundary.
- Explain the practical effect on independent change, operation, or ownership.
- Distinguish erosion from an intentional redesign and propose restoring or redefining the boundary.

## Why this matters

A boundary can remain visible in diagrams while gradually losing its operational value. Customers need evidence of the change and a choice about whether to repair the boundary or update the architecture.

## Evidence to use

Use baseline and current graphs, interface changes, schema access history, releases, and design decisions.

## Expected report output

A boundary evolution record with original purpose, dated deviations, affected guarantees, intent status, and proposed disposition.

## Completion and quality checks

Do not assume an undocumented change is accidental. Flag unresolved intent and avoid treating an obsolete boundary as inherently worth preserving.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
