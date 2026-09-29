# Single points of failure

**Section:** 10 · Reliability and failure architecture  
**Specification ID:** `AR-10-01`  
**Customer question:** Which individual failures can prevent an important capability from operating?

## What to include

- Identify candidate single points across processes, stores, queues, identity, configuration, networking, and control services.
- Define the failure scope and affected business capability for each candidate.
- Evaluate replicas, failover, shared dependencies, and common failure domains.
- Describe current mitigation, remaining exposure, and a verification or improvement action.

## Why this matters

Customers need to know where redundancy is absent or only apparent. A failure-domain view helps focus reliability investment on the parts that can stop important work.

## Evidence to use

Use observed or declared topology, replication and failover configuration, workflow dependencies, and recovery tests or incident evidence.

## Expected report output

A single-point register with component, failure domain, affected capability, redundancy, failover evidence, residual risk, and next action.

## Completion and quality checks

A single instance is not necessarily a business outage, and multiple replicas may share a failure domain. Do not infer tested failover from configuration alone.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
