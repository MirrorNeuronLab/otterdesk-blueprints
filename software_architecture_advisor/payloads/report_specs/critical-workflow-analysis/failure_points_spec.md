# Workflow failure points

**Section:** 09 · Critical workflow analysis  
**Specification ID:** `AR-09-03`  
**Customer question:** Where can this workflow fail, and what does the customer observe?

## What to include

- Identify failure-prone boundaries such as validation, remote calls, queue delivery, writes, and external side effects.
- Describe timeout, rejection, partial success, duplication, cancellation, and missing completion scenarios as applicable.
- Map failures to user-visible results, persisted state, alerts, and recovery actions.
- Highlight failures that are swallowed, misreported, or leave work in an ambiguous state.

## Why this matters

A workflow review should explain what happens when work does not complete normally. This gives customers specific reliability and support improvements rather than an abstract warning that dependencies may fail.

## Evidence to use

Use error paths, timeout settings, state changes, tests, operational logs, and supplied incident examples.

## Expected report output

A workflow failure table with step, failure mode, observable outcome, state consequence, detection, and recovery.

## Completion and quality checks

Differentiate an unhandled path found in code from a failure observed in production. Keep hypotheses explicit and avoid asserting the frequency of a failure without data.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
