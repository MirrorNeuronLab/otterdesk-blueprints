# Git churn

**Section:** 06 · Architecture hotspots  
**Specification ID:** `AR-06-02`  
**Customer question:** Which architectural areas absorb the most change?

## What to include

- Define the history window and measures such as changed lines, change frequency, or distinct change events.
- Aggregate changes by architectural component with rename, merge, generated-code, and bulk-formatting handling.
- Show trends, denominators, and whether activity reflects new work, migrations, or repeated maintenance.
- Highlight areas where active change intersects with structural risk or limited test protection.

## Why this matters

Churn directs attention toward architecture the team actually touches. It helps customers avoid spending scarce effort on difficult but stable areas while overlooking frequently changed boundaries.

## Evidence to use

Use version-control history and component ownership mappings. Add pull-request intent or issue classification only when available and reliable.

## Expected report output

A churn table or trend view with time window, component, change count, selected measure, exclusions, and interpretation.

## Completion and quality checks

Do not label frequent changes as defects or developer underperformance. Account for repository age, file moves, incomplete history, and different component sizes.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
