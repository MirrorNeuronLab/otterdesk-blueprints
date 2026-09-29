# Release risk

**Section:** 20 · Business impact  
**Specification ID:** `AR-20-02`  
**Customer question:** How does the architecture affect the chance or consequence of a problematic release?

## What to include

- Identify release coupling, compatibility requirements, data migrations, large blast radii, and weak rollback paths.
- Describe concrete failure scenarios and their user or operational consequences.
- Use available release history to distinguish observed patterns from plausible risk.
- Explain how proposed changes could reduce exposure and what release evidence would demonstrate improvement.

## Why this matters

Customers need to connect architecture decisions to confidence in shipping. Scenario-based release risk is more useful than asserting that a particular style is inherently safer.

## Evidence to use

Use deployment and rollback records, compatibility tests, change-impact analysis, migration history, and release-related incidents.

## Expected report output

A release-risk table with mechanism, affected releases or capabilities, evidence, mitigation, residual risk, and success measure.

## Completion and quality checks

Do not fabricate a probability of failure or classify all incidents after a release as caused by it. Distinguish reduced blast radius from reduced likelihood of introducing a defect.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
