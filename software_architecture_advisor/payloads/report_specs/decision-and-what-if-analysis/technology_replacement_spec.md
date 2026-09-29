# Technology replacement

**Section:** 16 · Decision and what-if analysis  
**Specification ID:** `AR-16-03`  
**Customer question:** What would replacing a database, queue, framework, or other platform actually affect?

## What to include

- Specify the current technology, candidate replacement, workload requirements, and comparison scope.
- Inventory explicit APIs and implicit semantic dependencies, including transactions, ordering, query behavior, and failure handling.
- Assess data migration, operational tooling, compatibility, performance validation, and retraining or ownership needs.
- Compare targeted adaptation, partial replacement, and full migration with a retain-current baseline.

## Why this matters

Customers need the true architectural switching cost, not just a feature checklist. Hidden semantic dependencies often determine whether a replacement is feasible and how it must be staged.

## Evidence to use

Use implementation and configuration, contracts, data models, operational procedures, supplied requirements, and dated primary documentation when a concrete comparison is performed.

## Expected report output

A replacement impact matrix and decision brief with required capabilities, incompatibilities, migration work, test plan, costs as assumptions, and alternatives.

## Completion and quality checks

Do not assume interchangeable APIs imply equivalent semantics. Do not invent current product features, licenses, prices, or benchmark results; verify them separately when populating the report.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
