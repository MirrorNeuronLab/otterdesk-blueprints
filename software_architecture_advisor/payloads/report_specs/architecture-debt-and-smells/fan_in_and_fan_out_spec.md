# Fan-in and fan-out

**Section:** 07 · Architecture debt and smells  
**Specification ID:** `AR-07-08`  
**Customer question:** Where do unusually broad dependency relationships create a practical design concern?

## What to include

- Define incoming and outgoing dependency counts at a specified component and edge granularity.
- Identify high or rapidly changing values relative to comparable components.
- Explain whether the relationships represent stable reuse, orchestration, scattered responsibilities, or boundary leakage.
- Link problematic cases to specific change, testing, or failure scenarios.

## Why this matters

Dependency breadth can highlight components requiring special review, but raw counts do not explain the risk. Contextual interpretation helps customers preserve useful reuse while reducing avoidable coupling.

## Evidence to use

Use the typed dependency graph, public interfaces, component responsibilities, and change or workflow evidence.

## Expected report output

A dependency-breadth table with counts, edge semantics, comparison basis, representative edges, interpretation, and suggested action.

## Completion and quality checks

Do not use arbitrary cutoffs as proof of debt. Separate incoming use of a stable API from consumers that depend on internal implementation details.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
