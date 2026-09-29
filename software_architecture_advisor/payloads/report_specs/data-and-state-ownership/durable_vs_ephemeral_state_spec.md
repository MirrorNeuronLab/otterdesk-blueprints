# Durable versus ephemeral state

**Section:** 08 · Data and state ownership  
**Specification ID:** `AR-08-06`  
**Customer question:** What survives process loss, and what must be reconstructed?

## What to include

- Classify domain data, queues, checkpoints, session state, local files, caches, and in-memory progress.
- State the failure scope each durability claim covers: process restart, host loss, storage loss, or broader outage.
- Describe persistence boundaries, flush or acknowledgement behavior, and reconstruction mechanisms.
- Identify important work or state that can be lost between durable transitions.

## Why this matters

Customers need to understand what restart and recovery actually preserve. A precise failure scope prevents a persistent-looking component from being mistaken for protection against every kind of loss.

## Evidence to use

Use storage and queue configuration, transaction boundaries, checkpoint code, deployment volumes, and verified recovery tests.

## Expected report output

A state-durability matrix with state, location, persistence mechanism, covered failure scope, potential loss window, and reconstruction path.

## Completion and quality checks

Do not infer end-to-end durability from a storage product name. Acknowledgement and replication settings, deployment placement, and observed tests must support the claim.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
