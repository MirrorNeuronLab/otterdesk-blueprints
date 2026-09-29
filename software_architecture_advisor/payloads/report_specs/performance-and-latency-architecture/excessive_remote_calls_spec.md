# Excessive remote calls

**Section:** 12 · Performance and latency architecture  
**Specification ID:** `AR-12-03`  
**Customer question:** Where does the architecture perform avoidable network interactions?

## What to include

- Measure or estimate remote calls per workflow with the method and workload made explicit.
- Identify repeated lookups, per-item request loops, redundant validation, and duplicate fetches.
- Explain latency, quota, bandwidth, or failure-exposure consequences for each pattern.
- Compare batching, request shaping, local reuse, caching, or contract changes.

## Why this matters

Customers need to know which communication patterns impose avoidable work. A concrete call-level explanation can lead to a contained improvement without requiring a wholesale service redesign.

## Evidence to use

Use traces, client instrumentation, call sites, loop structure, request schemas, and supplied service limits.

## Expected report output

A remote-call amplification table with workflow, call pattern, observed or inferred count, consequence, alternative, and validation.

## Completion and quality checks

Do not treat every remote call as waste. Verify required freshness and behavior before recommending caching, and preserve partial-failure semantics when batching.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
