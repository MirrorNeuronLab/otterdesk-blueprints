# Chatty service boundaries

**Section:** 12 · Performance and latency architecture  
**Specification ID:** `AR-12-04`  
**Customer question:** Do service contracts force repeated back-and-forth to complete one coherent task?

## What to include

- Identify workflow segments with repeated alternating calls between the same services.
- Show whether the interaction reflects a fragmented contract, misplaced responsibility, or a legitimate protocol.
- Assess release, error-handling, latency, and ownership implications of the boundary.
- Compare coarser contracts, local orchestration, data projections, or boundary changes.

## Why this matters

A chatty boundary can indicate that responsibility is split at the wrong place. Customers need an architectural explanation of the pattern, not just a recommendation to reduce request counts.

## Evidence to use

Use sequence traces, API contracts, domain responsibilities, transaction assumptions, and change history.

## Expected report output

A boundary-level interaction view with task, call sequence, reason for repeated crossings, alternatives, and tradeoffs.

## Completion and quality checks

Keep this distinct from individual redundant calls. Do not recommend merging services without assessing isolation, scaling, security, and ownership benefits of the current separation.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
