# Validation plan

**Section:** 18 · Concrete prioritized recommendations  
**Specification ID:** `AR-18-06`  
**Customer question:** How will we know the recommendation produced the intended improvement?

## What to include

- Define the property or outcome to improve and its current baseline or baseline measurement task.
- Specify structural checks, tests, experiments, or operational observations appropriate to that property.
- Set measurable acceptance conditions, observation scope, and guardrails against regressions.
- State responsibility, evaluation timing, and what result would reject or revise the recommendation.

## Why this matters

Customers need to distinguish implemented changes from successful improvements. A validation plan turns the recommendation into a falsifiable claim and protects important existing behavior.

## Evidence to use

Use the finding mechanism, available baselines, customer requirements, test capabilities, and the migration plan.

## Expected report output

A validation table with hypothesis, baseline, method, success criterion, regression guardrails, evidence artifact, and owner status.

## Completion and quality checks

Do not define success only as code merged or a diagram simplified. Avoid invented thresholds; proposed thresholds must be labeled and approved before they become release gates.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

## Related specifications

- [Acceptance criteria](../implementation-ready-work-packages/acceptance_criteria_spec.md)

---

[Section contents](README.md) · [Full index](../INDEX.md)
