# Synchronization points

**Section:** 12 · Performance and latency architecture  
**Specification ID:** `AR-12-06`  
**Customer question:** Where do locks, barriers, transactions, or coordination waits delay independent work?

## What to include

- Identify global or shared locks, transaction serialization, barriers, leader decisions, and required joins.
- Explain the invariant protected and the scope and duration of the synchronization.
- Assess contention, waiting, deadlock potential where evidenced, and effects on tail latency.
- Compare narrower locking, different ownership, asynchronous coordination, or unchanged design with better limits.

## Why this matters

Synchronization may be essential for correctness, but overly broad coordination can constrain responsiveness. Customers need to understand the protected invariant before considering a performance change.

## Evidence to use

Use lock and transaction code, database wait observations, concurrency profiles, traces, and tests for ordering or isolation.

## Expected report output

A synchronization register with point, protected invariant, participants, wait evidence, performance consequence, and safe alternative.

## Completion and quality checks

Do not remove synchronization simply to reduce delay. Distinguish structural deadlock possibilities from observed deadlocks and preserve the required consistency semantics.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
