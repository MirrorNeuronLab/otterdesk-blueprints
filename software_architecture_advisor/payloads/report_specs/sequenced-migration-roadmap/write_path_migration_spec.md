# Write-path migration

**Section:** 19 · Sequenced migration and refactoring roadmap  
**Specification ID:** `AR-19-05`  
**Customer question:** How will authority for state changes move without losing or duplicating effects?

## What to include

- Inventory all writers, including background, administrative, and migration paths.
- Define the authoritative writer at each stage and the mechanism for replication, forwarding, or temporary dual operation.
- Specify ordering, deduplication, backfill, reconciliation, and handling of in-flight work.
- Define cutover gates, divergence response, and irreversible points.

## Why this matters

Changing write authority is a correctness-critical part of a migration. Customers need a precise account of who can write when and how inconsistent results will be detected and repaired.

## Evidence to use

Use writer and source-of-truth inventories, transaction and event behavior, idempotency analysis, migration tooling, and failure-window tests.

## Expected report output

A write cutover plan with stages, authority, replication semantics, reconciliation, in-flight handling, exit gates, and rollback constraints.

## Completion and quality checks

Do not recommend uncontrolled dual writes or assume rollback restores already-mutated data. Include failure scenarios around every authority transition.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
