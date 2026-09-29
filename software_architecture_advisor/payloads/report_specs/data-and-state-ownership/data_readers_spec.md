# Data readers

**Section:** 08 · Data and state ownership  
**Specification ID:** `AR-08-03`  
**Customer question:** Who depends on the meaning, shape, and freshness of this data?

## What to include

- List direct and derived readers, including services, reporting jobs, caches, exports, and external consumers.
- Describe the interface or access path and the fields or semantics relied upon.
- Record freshness, ordering, completeness, and compatibility expectations.
- Identify readers that bypass an intended owner or depend on undocumented representation.

## Why this matters

Reader obligations define the real compatibility surface of a data change. This helps customers avoid breaking analytics, exports, or infrequent operational workflows that do not appear on a primary request path.

## Evidence to use

Use queries, API consumers, transformations, subscriptions, reports, and authorized access or lineage records.

## Expected report output

A reader matrix with entity, consumer, access path, semantic dependency, freshness requirement, and migration obligation.

## Completion and quality checks

Absence from an application dependency graph is not evidence of no readers. State coverage for direct database access and external consumers.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
