# Cache topology and invalidation

**Section:** 08 · Data and state ownership  
**Specification ID:** `AR-08-05`  
**Customer question:** Where is data cached, and what keeps cached behavior acceptably correct?

## What to include

- Inventory local, shared, edge, and application-level caches with keys and source data.
- Describe population, expiry, invalidation, eviction, and refresh mechanisms.
- Explain staleness tolerance, cache misses, cache unavailability, and concurrent refresh behavior.
- Identify coupling through shared keys, serialization, and invalidation responsibilities.

## Why this matters

A cache changes correctness and failure behavior as well as performance. This view helps customers evaluate whether a data change or outage can leave consumers using incompatible or stale state.

## Evidence to use

Use cache access code, key construction, configuration, update paths, tests, and supplied runtime hit, miss, and refresh observations.

## Expected report output

A cache inventory and flow map with owner, source, consumers, freshness contract, invalidation mechanism, and failure behavior.

## Completion and quality checks

An expiry setting alone does not prove an end-to-end freshness guarantee. Label inferred cache behavior and avoid assuming all deployments share identical settings.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
