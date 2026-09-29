# Critical workflow path

**Section:** 09 · Critical workflow analysis  
**Specification ID:** `AR-09-02`  
**Customer question:** Which dependent steps determine when this workflow can complete?

## What to include

- Identify prerequisite chains, parallel branches, joins, queues, and required external responses.
- Distinguish the logically necessary path from the measured latency-dominant path.
- Explain which steps could overlap and which depend on data, state, or business ordering.
- Record missing timing evidence and candidate measurements or experiments.

## Why this matters

Customers need to know which changes could actually shorten or simplify the workflow. Identifying dependency constraints prevents effort being spent on a step that does not determine completion.

## Evidence to use

Use workflow structure, asynchronous scheduling, trace timings, queue observations, and representative test execution where available.

## Expected report output

An annotated critical-path view with dependency reasons, measured or unknown durations, parallelism constraints, and improvement hypotheses.

## Completion and quality checks

Do not call the longest-looking code path the latency bottleneck. Account for waits and joins and avoid summing durations of parallel steps.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

## Related specifications

- [Critical latency paths](../performance-and-latency-architecture/critical_latency_paths_spec.md)

---

[Section contents](README.md) · [Full index](../INDEX.md)
