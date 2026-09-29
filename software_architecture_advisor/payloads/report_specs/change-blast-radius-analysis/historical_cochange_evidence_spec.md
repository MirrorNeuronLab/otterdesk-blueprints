# Historical co-change evidence

**Section:** 05 · Change blast-radius analysis  
**Specification ID:** `AR-05-08`  
**Customer question:** What past changes suggest additional review targets for this change?

## What to include

- Find prior changes similar in target or intent and identify components changed alongside them.
- Define the history window, change grouping, exclusions, and association measure.
- Show representative examples and distinguish repeated patterns from one-off bulk changes.
- Use historical associations to suggest additional review or tests, not to assert dependency without corroboration.

## Why this matters

History can reveal coordination that is invisible to static analysis, including documentation, deployment, and data migration work. It is most useful as a source of concrete review targets.

## Evidence to use

Use commits or pull requests, rename-aware file history, linked issues where available, and actual diffs. Record shallow history and missing repositories.

## Expected report output

A scenario-specific co-change table with associated component, sample count, history window, representative changes, interpretation, and follow-up.

## Completion and quality checks

State denominators and filtering rules. Do not turn correlation into a probability of failure or conflate this scenario evidence with the report-wide co-change inventory.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

## Related specifications

- [Temporal and co-change coupling](../hidden-coupling/temporal_and_cochange_coupling_spec.md)

---

[Section contents](README.md) · [Full index](../INDEX.md)
