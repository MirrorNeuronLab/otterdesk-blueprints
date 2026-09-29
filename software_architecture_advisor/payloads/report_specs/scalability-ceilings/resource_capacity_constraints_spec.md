# Resource capacity constraints

**Section:** 11 · Scalability ceilings  
**Specification ID:** `AR-11-03`  
**Customer question:** Which CPU, memory, network, storage, database, or quota limits matter to growth?

## What to include

- Inventory relevant capacity and configured limits, with environment and observation time.
- Relate resource demand to workload dimensions, including per-request, per-worker, and per-data-unit costs where measurable.
- Identify headroom, burst behavior, contention, and limits that cannot be removed by replication alone.
- Describe uncertainty, measurement gaps, and candidate capacity or demand-reduction actions.

## Why this matters

Resource-specific analysis turns scaling discussions into concrete planning inputs. It also prevents customers from assuming that adding compute will resolve a limit imposed by state, I/O, or an external quota.

## Evidence to use

Use supplied telemetry, profiling, runtime and database settings, deployment limits, and documented service quotas available within the review scope.

## Expected report output

A capacity table with resource, limit, observed demand, workload basis, headroom, measurement date, and recommended check.

## Completion and quality checks

State units and observation windows. Do not derive peak capacity from idle measurements or use current prices and quotas without supplied or separately verified sources.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
