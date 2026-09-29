# First limiting component

**Section:** 11 · Scalability ceilings  
**Specification ID:** `AR-11-01`  
**Customer question:** Under a defined growth scenario, which component is likely to constrain useful throughput first?

## What to include

- Define the baseline workload, growth dimension, concurrency, data size, and required service behavior.
- Compare candidate limits across processing, storage, queues, connection pools, and external quotas.
- Identify the first plausible constraint and explain the chain from load growth to degraded outcome.
- Show alternative candidates and the measurements needed when the evidence cannot establish an ordering.

## Why this matters

Customers need a targeted capacity decision rather than a general statement that the system may not scale. An explicit workload makes the conclusion useful for planning and test design.

## Evidence to use

Use supplied load and resource observations, benchmark results, limits in configuration, and workflow demand models. Label extrapolation and unknown production conditions.

## Expected report output

A scenario-based constraint comparison with baseline, candidate component, limiting resource, estimated or measured threshold, confidence, and next experiment.

## Completion and quality checks

Do not present a code-only hypothesis as a measured capacity ceiling. A first limit may change with workload mix, deployment size, or external service behavior.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
