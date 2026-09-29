# Code complexity

**Section:** 06 · Architecture hotspots  
**Specification ID:** `AR-06-01`  
**Customer question:** Where is implementation complexity concentrated at an architectural level?

## What to include

- State the complexity measures, analysis granularity, supported languages, and aggregation method.
- Show component-level distributions and concentrated outliers rather than only system-wide averages.
- Connect complex regions to responsibilities, critical workflows, and practical change or testing difficulty.
- Separate generated code, vendor code, and unavoidable domain complexity from actionable design complexity.

## Why this matters

Complexity is useful when it identifies where a change requires unusually difficult reasoning. Architectural aggregation helps customers focus on a subsystem or boundary instead of receiving another long list of complicated functions.

## Evidence to use

Use reproducible source analysis, component mappings, representative code paths, and relevant tests. Record tool versions, unsupported constructs, and exclusions.

## Expected report output

A component complexity table with measure definitions, distributions, representative locations, architectural interpretation, and review priority.

## Completion and quality checks

Do not use an unexplained universal threshold or compare incompatible measures across languages. High complexity alone does not establish poor architecture or justify a rewrite.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
