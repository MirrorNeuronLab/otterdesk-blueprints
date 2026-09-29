# Data and schema dependencies

**Section:** 05 · Change blast-radius analysis  
**Specification ID:** `AR-05-05`  
**Customer question:** Which data consumers, migrations, and invariants are affected?

## What to include

- Identify changed entities, fields, indexes, constraints, event payloads, and serialization formats.
- Map readers, writers, derived data, caches, exports, and background jobs that depend on them.
- Explain migration ordering, mixed-version compatibility, backfill, and consistency risks.
- Specify validation and reconciliation needed before and after the change.

## Why this matters

Data dependencies often survive application boundaries and release cycles. This analysis helps prevent a safe-looking code change from causing irreversible data damage or incompatibility for an overlooked consumer.

## Evidence to use

Use schema definitions, migrations, queries, access wrappers, transformation code, data lineage, and supplied operational migration records.

## Expected report output

A data-impact matrix and migration note: entity, dependency, invariant, compatibility window, backfill requirement, and verification.

## Completion and quality checks

Distinguish logical schema changes from actual deployed data state. Do not assume destructive migrations are reversible or dual writes are consistent without a specified mechanism.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
