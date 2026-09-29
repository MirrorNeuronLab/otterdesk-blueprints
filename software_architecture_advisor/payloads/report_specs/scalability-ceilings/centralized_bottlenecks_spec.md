# Centralized bottlenecks

**Section:** 11 · Scalability ceilings  
**Specification ID:** `AR-11-04`  
**Customer question:** Which centralized operations can cap throughput or prevent independent scaling?

## What to include

- Identify shared coordinators, queues, stores, schedulers, global locks, and serial decision points.
- Explain their role in the critical work path and the demand that grows with the system.
- Evaluate partitioning, replication, batching, caching, or removal of unnecessary central work.
- Record correctness, ordering, and operational tradeoffs of distributing the responsibility.

## Why this matters

Customers need to know whether growth requires more instances or a change to the unit of coordination. A centralized limit can remain unchanged even when the surrounding services scale out.

## Evidence to use

Use execution paths, topology, concurrency design, coordination state, throughput observations, and relevant invariants.

## Expected report output

A centralized-constraint table with operation, scaling dependency, evidence, proposed alternatives, preserved invariants, and validation.

## Completion and quality checks

Central location is not proof of a throughput bottleneck. Distinguish this capacity finding from centralization debt and single-point-of-failure analysis.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
