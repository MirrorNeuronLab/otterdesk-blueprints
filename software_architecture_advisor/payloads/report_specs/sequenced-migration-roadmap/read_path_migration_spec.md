# Read-path migration

**Section:** 19 · Sequenced migration and refactoring roadmap  
**Specification ID:** `AR-19-04`  
**Customer question:** How will readers move to the new interface or store without silent behavior changes?

## What to include

- Inventory readers and define the destination contract, data freshness, and semantic equivalence requirements.
- Describe phased routing, comparison or shadow reads where appropriate, and compatibility adapters.
- Specify mismatch detection, reconciliation, performance checks, and consumer-specific rollout gates.
- Identify fallback conditions and when old read paths can be removed.

## Why this matters

Read migration provides an opportunity to verify a new representation before all dependencies move. Customers need to preserve meaning and freshness, not merely make a new query return data.

## Evidence to use

Use reader inventories, schema mappings, contract tests, representative data cases, and measured comparison results when available.

## Expected report output

A reader-by-reader migration table with destination, semantic checks, rollout method, success gate, and fallback.

## Completion and quality checks

Read migration before write migration is a candidate strategy, not a universal requirement. Justify the order and account for side effects, sensitive data, or cost in shadow-read designs.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
