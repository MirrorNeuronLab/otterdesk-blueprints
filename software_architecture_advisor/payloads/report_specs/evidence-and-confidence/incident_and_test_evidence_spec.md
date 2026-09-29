# Incident and test evidence

**Section:** 21 · Evidence and confidence  
**Specification ID:** `AR-21-05`  
**Customer question:** Which failures or checks demonstrate the claimed behavior?

## What to include

- For incidents, record the event, affected capability, timeline, confirmed cause, and unresolved hypotheses.
- For tests, record test identity, version, environment, inputs, expected behavior, execution status, and actual result if available.
- Link the evidence to the specific claim or invariant it supports.
- Distinguish test existence, test execution, passing results, and demonstrated production behavior.

## Why this matters

Customers need to know whether a claim was observed, tested, or merely proposed for testing. This distinction is especially important for recovery, compatibility, and safety-related assurances.

## Evidence to use

Use actual incident reviews, test definitions, test run artifacts, logs, and reproduction records supplied or accessed within the authorized review.

## Expected report output

An incident or test evidence record with source ID, scope, result, supported claim, causal status, and limitations.

## Completion and quality checks

A passing test supports only the behavior and conditions it checks. Do not treat a suspected incident cause as established or report recommended tests as already executed.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
