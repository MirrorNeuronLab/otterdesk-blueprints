# Bottleneck mechanisms

**Section:** 11 · Scalability ceilings  
**Specification ID:** `AR-11-02`  
**Customer question:** Why would a proposed bottleneck constrain the system?

## What to include

- Describe the mechanism, such as serialized work, expensive repeated processing, bounded connections, queue saturation, or data contention.
- Trace how workload demand reaches the constrained resource and affects completion, latency, or error rate.
- Distinguish service time, waiting time, backlog growth, and downstream effects.
- State the conditions under which the mechanism matters and the intervention that could change it.

## Why this matters

A mechanism makes a scaling claim testable. It helps customers choose between adding capacity, changing a workflow, reducing demand, or redesigning a boundary.

## Evidence to use

Use code paths, resource and concurrency configuration, profiles, trace timing, queue observations, and controlled load-test results.

## Expected report output

A bottleneck explanation with demand path, limiting operation, observed or hypothesized behavior, assumptions, and validation experiment.

## Completion and quality checks

Do not infer saturation from high utilization alone. Explain which resource constrains useful work and what evidence would falsify the hypothesis.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
