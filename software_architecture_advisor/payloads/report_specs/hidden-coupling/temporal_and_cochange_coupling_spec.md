# Temporal and co-change coupling

**Section:** 04 · Hidden coupling  
**Specification ID:** `AR-04-03`  
**Customer question:** Which components must be used in a particular order or repeatedly change together?

## What to include

- Separate runtime ordering requirements from historical co-change; report them as different kinds of coupling.
- For temporal coupling, identify required call or event order and what fails when the order changes.
- For co-change, define the history window, change unit, filtering rules, and strength of association.
- Investigate likely reasons for each association and name plausible confounders such as bulk formatting or migrations.

## Why this matters

Both forms can hide obligations that are absent from a simple import graph. Distinguishing them prevents historical correlation from being mistaken for a runtime dependency.

## Evidence to use

Use state transitions, workflow tests, protocol documentation, commit or pull-request history, and carefully selected change examples. Record merge and bulk-change handling.

## Expected report output

Separate temporal-dependency and co-change tables, each with components, evidence, interpretation, consequence, and confidence.

## Completion and quality checks

Do not claim causation from co-change alone. Report sample sizes and history gaps, and avoid combining runtime order and co-change into one unexplained score.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
