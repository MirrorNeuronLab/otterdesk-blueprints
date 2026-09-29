# Restart and retry behavior

**Section:** 10 · Reliability and failure architecture  
**Specification ID:** `AR-10-05`  
**Customer question:** Can interrupted work resume safely after a process or host restarts?

## What to include

- Describe what execution state survives and how unfinished work is rediscovered or reassigned.
- Trace leases, locks, checkpoints, acknowledgements, and handling of ambiguous completion.
- Explain interactions between restart recovery, scheduled retries, and duplicate execution.
- Identify stale ownership, lost work, repeated effects, and startup ordering risks.

## Why this matters

Customers need to know whether recovery resumes work or merely restarts software. This distinction is central to long-running jobs, asynchronous workflows, and state-changing operations.

## Evidence to use

Use lifecycle code, durable-state mappings, queue acknowledgement settings, lease logic, checkpoint handling, and restart tests.

## Expected report output

A restart scenario table with interruption point, surviving state, rediscovery mechanism, duplicate protection, completion behavior, and gaps.

## Completion and quality checks

Do not claim recovery from host or storage loss based only on a successful process restart. Separate intended recovery logic from behavior verified by tests.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
