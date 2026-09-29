# Sources of truth

**Section:** 08 · Data and state ownership  
**Specification ID:** `AR-08-04`  
**Customer question:** Which representation is authoritative when copies disagree?

## What to include

- Identify the authoritative source for each important entity, attribute group, or lifecycle stage.
- Map replicas, caches, projections, exports, and derived views back to that authority.
- Explain update authority, reconciliation rules, and behavior when sources disagree.
- Record cases where authority changes over time or is unresolved.

## Why this matters

Customers need a clear answer when multiple stores contain similar information. Explicit authority makes recovery, reconciliation, and migration decisions possible without relying on undocumented operator judgment.

## Evidence to use

Use domain rules, write ownership, replication or event processing configuration, reconciliation jobs, and operational procedures.

## Expected report output

An authority map with data scope, source of truth, dependent representations, synchronization mechanism, and conflict-resolution rule.

## Completion and quality checks

Avoid claiming one universal source of truth when authority is attribute-specific or lifecycle-specific. Do not infer authority solely from a table name or apparent freshness.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
