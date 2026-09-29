# Coupling trends

**Section:** 14 · Architecture evolution  
**Specification ID:** `AR-14-01`  
**Customer question:** Are component dependencies becoming more or less constraining over time?

## What to include

- Select comparable versions or time windows and define the dependency and co-change measures used.
- Track changes in cross-boundary edges, shared state, cycles, and coordinated change where available.
- Normalize or explain changes caused by system growth, renamed components, or analysis coverage.
- Highlight consequential trends and connect them to specific architectural changes.

## Why this matters

Customers need to distinguish a persistent direction of change from one alarming snapshot. A trend can show whether current development practices are strengthening or eroding intended boundaries.

## Evidence to use

Use versioned dependency graphs, rename-aware history, stable component mappings, and relevant design or release records.

## Expected report output

A coupling trend view with baseline, windows, metric definitions, coverage, significant changes, and interpretation.

## Completion and quality checks

Use compatible graph semantics across snapshots. Do not infer improvement from fewer edges when code was excluded or a repository moved outside the review scope.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
