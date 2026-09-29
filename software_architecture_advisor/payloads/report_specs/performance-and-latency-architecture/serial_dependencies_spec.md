# Serial dependencies

**Section:** 12 · Performance and latency architecture  
**Specification ID:** `AR-12-02`  
**Customer question:** Which sequential steps are necessary, and which could be overlapped or removed?

## What to include

- Identify ordered call chains, waits, joins, and per-item loops across important workflows.
- Explain the data, state, or business requirement that forces each ordering relationship.
- Identify avoidable sequencing, redundant prerequisites, and opportunities for safe concurrency.
- Assess impacts on consistency, resource demand, error handling, and cancellation.

## Why this matters

A customer can gain more from changing the dependency structure than from making each operation slightly faster. The analysis must preserve correctness rather than recommending parallelism indiscriminately.

## Evidence to use

Use workflow structure, awaited calls, transaction boundaries, trace timing, and tests covering ordering constraints.

## Expected report output

A serial-chain table with step, prerequisite reason, measured or unknown delay, concurrency option, and correctness checks.

## Completion and quality checks

Do not assume independent-looking calls are safe to run concurrently. Account for shared state, rate limits, load amplification, and changes to failure semantics.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
