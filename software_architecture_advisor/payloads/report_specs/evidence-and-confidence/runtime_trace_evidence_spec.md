# Runtime trace evidence

**Section:** 21 · Evidence and confidence  
**Specification ID:** `AR-21-02`  
**Customer question:** What observed execution supports the architectural behavior or timing claim?

## What to include

- Record environment, timestamp or window, workload, trace or correlation ID, and sampling coverage.
- Identify the relevant spans, boundaries, status, timing, and correlated state transitions.
- Explain what the observation supports and which alternative paths were not observed.
- Record instrumentation gaps, clock concerns, sampling bias, and redaction of sensitive payloads.

## Why this matters

Runtime evidence can establish that a path actually occurred under specific conditions. Customers need enough context to avoid generalizing one trace into a claim about every execution.

## Evidence to use

Use supplied or authorized traces, logs, client observations, and telemetry tied to the reviewed deployment. Preserve provenance and access restrictions.

## Expected report output

A trace evidence record with observation scope, relevant path or spans, supported claim, timing basis, and limitations.

## Completion and quality checks

Do not infer complete traffic coverage from sampled traces. Distinguish observed request completion from asynchronous job completion and avoid revealing sensitive trace payloads.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
