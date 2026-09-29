# Critical latency paths

**Section:** 12 · Performance and latency architecture  
**Specification ID:** `AR-12-01`  
**Customer question:** Which architectural stages account for delay in important user or job outcomes?

## What to include

- Define the measured outcome, workload, environment, time window, and relevant latency distribution.
- Decompose end-to-end time into processing, queueing, remote waits, data access, and completion signaling.
- Show critical dependencies and distinguish parallel work from sequential delay.
- Identify measured contributors, uncertain gaps, and candidate changes with testable expected effects.

## Why this matters

Customers care about the time to a useful result. An end-to-end breakdown prevents optimization of a small local operation while the dominant delay remains in waiting or coordination.

## Evidence to use

Use correlated traces, profiling, queue metrics, client timing, and representative benchmarks supplied for the reviewed environment.

## Expected report output

A latency budget or path breakdown with distribution, sample scope, stage contributions, evidence quality, and proposed experiment.

## Completion and quality checks

Do not add independent percentile values to claim an end-to-end percentile. Where timing evidence is absent, present a measurement plan and structural hypotheses rather than numeric conclusions.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
