# Required tests

**Section:** 23 · Implementation-ready work packages  
**Specification ID:** `AR-23-06`  
**Customer question:** What checks must accompany this work before it can be accepted?

## What to include

- Specify tests for preserved behavior, changed contracts, architectural rules, and identified failure scenarios.
- List existing tests to run and new tests to create, with actual identifiers or clearly labeled proposed names.
- Define inputs, expected outcomes, environment, fixtures, and relevant concurrency or failure conditions.
- Require recording execution status and results, including blocked or skipped checks.

## Why this matters

Customers need evidence that a work package preserved the intended guarantees. Risk-linked tests make the task reviewable and reduce reliance on the implementer’s assurance that it looks correct.

## Evidence to use

Use the validation plan, blast-radius test map, contracts, invariants, and repository test configuration.

## Expected report output

A required-test matrix with test or scenario, protected risk, setup, expected result, execution command when verified, and result artifact.

## Completion and quality checks

Do not claim tests pass unless they were executed. New test names must be labeled proposed, and passing unit tests must not substitute for required migration or compatibility checks.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
