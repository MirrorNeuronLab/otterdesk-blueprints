# Failure cascades

**Section:** 10 · Reliability and failure architecture  
**Specification ID:** `AR-10-02`  
**Customer question:** How can one local failure spread to otherwise healthy parts of the system?

## What to include

- Trace propagation through synchronous waits, shared pools, retries, queues, and shared state.
- Describe the initiating failure, amplification mechanism, and affected components.
- Evaluate containment such as timeouts, concurrency limits, isolation, backpressure, or degraded operation.
- Identify a safe verification approach and observable signs of containment or spread.

## Why this matters

The customer needs to understand why a small outage could become a broader service disruption. Mechanism-based analysis points to containment improvements rather than simply recommending more replicas.

## Evidence to use

Use call topology, resource pools, retry and timeout configuration, queue behavior, load tests, and incident sequences.

## Expected report output

A failure-propagation view and scenario table with trigger, propagation path, amplifier, containment, evidence, and remediation.

## Completion and quality checks

A dependency path alone does not prove a cascade. State assumptions about load and timing and do not conduct disruptive tests without separate authorization.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
