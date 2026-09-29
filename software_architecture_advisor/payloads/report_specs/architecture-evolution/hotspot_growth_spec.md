# Hotspot growth

**Section:** 14 · Architecture evolution  
**Specification ID:** `AR-14-02`  
**Customer question:** Which architectural hotspots are emerging, worsening, or improving?

## What to include

- Compare hotspot signals across consistent observation windows and component definitions.
- Identify new hotspots, persistent hotspots, and areas where a previous intervention changed the signals.
- Explain whether growth reflects added responsibility, increased use, concentrated maintenance, or measurement changes.
- Link the trend to a specific decision, such as investigation, containment, or continued observation.

## Why this matters

Customers need to know whether a problem is stable or becoming harder to address. Evolutionary hotspot analysis can guide timing without treating every currently complex component as equally urgent.

## Evidence to use

Use historical versions of complexity, churn, defect, dependency, criticality, and test-gap evidence with matching windows.

## Expected report output

A hotspot evolution table with component, previous and current signals, explanatory changes, confidence, and recommended response.

## Completion and quality checks

Do not compare scores generated with different weighting or missing-data rules without recalculation or a clear caveat. A growing codebase alone does not prove worsening risk.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
