# Shared resource contention

**Section:** 11 · Scalability ceilings  
**Specification ID:** `AR-11-05`  
**Customer question:** Where do workloads interfere because they compete for the same resources?

## What to include

- Identify shared pools, database locks, storage bandwidth, compute, memory, quotas, and queues.
- Map competing workloads and describe burst patterns, priority, fairness, and isolation.
- Explain possible noisy-neighbor, starvation, or head-of-line effects under specific conditions.
- Compare isolation, admission control, scheduling, prioritization, and capacity changes.

## Why this matters

A service may have enough average capacity while still failing important work because another workload consumes a shared resource. This analysis supports customer decisions about isolation and predictable operation.

## Evidence to use

Use resource-pool configuration, queue and lock observations, workload traces, deployment placement, and contention tests or incidents.

## Expected report output

A contention matrix with resource, competing workloads, interference mechanism, impact, evidence, and mitigation option.

## Completion and quality checks

Do not infer contention merely because workloads share a host or database. Identify a contested resource and distinguish observed interference from a scenario to test.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
