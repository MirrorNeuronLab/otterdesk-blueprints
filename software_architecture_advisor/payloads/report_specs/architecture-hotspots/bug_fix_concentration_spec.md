# Bug-fix concentration

**Section:** 06 · Architecture hotspots  
**Specification ID:** `AR-06-05`  
**Customer question:** Where does corrective work repeatedly accumulate?

## What to include

- Define how changes are classified as defect fixes and describe classification reliability.
- Aggregate fix activity by component, defect class, severity where known, and time window.
- Show representative fixes and recurring architectural mechanisms rather than just counts.
- Compare absolute fix counts with change volume or another explicitly stated exposure measure.

## Why this matters

Recurring corrective work can help customers identify architecture that creates ongoing friction. Linking fixes to mechanisms makes it possible to distinguish a recurring design issue from ordinary implementation mistakes.

## Evidence to use

Use linked issues, pull-request labels and descriptions, commit diffs, tests, and incident records. Treat keyword-only classifications as uncertain.

## Expected report output

A defect-concentration table with component, sample size, classification method, exposure denominator, recurring mechanisms, and evidence examples.

## Completion and quality checks

Do not equate every commit containing fix with a production defect. Report missing labels and avoid attributing blame to individual contributors.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
