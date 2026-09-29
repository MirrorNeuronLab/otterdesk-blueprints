# Retry and idempotency behavior

**Section:** 09 · Critical workflow analysis  
**Specification ID:** `AR-09-06`  
**Customer question:** Can this workflow be retried without losing work or duplicating effects?

## What to include

- Identify retries at clients, gateways, workers, queues, and application handlers.
- Describe retry conditions, limits, backoff, timeout interaction, and deduplication scope.
- Trace idempotency keys, effect ordering, persistence, retention, and concurrent duplicate handling.
- Show failure windows where a retry can repeat an external or internal side effect.

## Why this matters

Retries are only useful when their semantics match the work being repeated. Customers need to understand whether an ambiguous response can become a duplicate charge, duplicated job, or lost state transition.

## Evidence to use

Use retry configuration, handler logic, idempotency storage, queue settings, side-effect clients, and duplicate-delivery or failure-window tests.

## Expected report output

A retry and idempotency matrix by workflow step with trigger, policy, effect, key scope, failure window, and verification.

## Completion and quality checks

An idempotency key alone is not proof of safe retry. Do not claim exactly-once end-to-end execution without specifying and verifying the relevant boundary and failure assumptions.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

## Related specifications

- [Restart and retry behavior](../reliability-and-failure-architecture/restart_and_retry_behavior_spec.md)

---

[Section contents](README.md) · [Full index](../INDEX.md)
