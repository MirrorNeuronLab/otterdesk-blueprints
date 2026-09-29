# Consistency and disagreement

**Section:** 08 · Data and state ownership  
**Specification ID:** `AR-08-07`  
**Customer question:** Can components hold conflicting views, and how is disagreement resolved?

## What to include

- Identify replicated, cached, derived, and multi-writer data representations.
- Describe required invariants and the permitted consistency or staleness behavior.
- Trace update ordering, duplication, conflict detection, and reconciliation paths.
- Provide concrete disagreement scenarios and explain their user-visible consequences.

## Why this matters

Customers need to know whether inconsistency is an accepted temporary state or a correctness failure. This distinction determines which changes need stronger coordination and which can tolerate asynchronous convergence.

## Evidence to use

Use transaction boundaries, event handlers, version fields, conflict rules, reconciliation jobs, and tests or incidents demonstrating relevant sequences.

## Expected report output

A consistency scenario table with representations, invariant, disagreement trigger, permitted window, detection, and resolution.

## Completion and quality checks

Do not use eventual consistency as a complete explanation. Specify how convergence happens and what occurs when messages or reconciliation work are delayed indefinitely.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
