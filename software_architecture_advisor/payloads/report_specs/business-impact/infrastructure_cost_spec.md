# Infrastructure cost

**Section:** 20 · Business impact  
**Specification ID:** `AR-20-05`  
**Customer question:** Which architectural choices drive recurring infrastructure cost, and what could change it?

## What to include

- Define the cost boundary, workload, environment, period, and included compute, storage, network, managed service, and operational costs.
- Link cost drivers to specific demand patterns, duplication, data movement, idle capacity, or placement choices.
- Compare alternatives using explicit usage assumptions and sourced or customer-supplied unit costs.
- Include transition cost, ongoing operations, reliability tradeoffs, and sensitivity to utilization.

## Why this matters

Customers need to evaluate total economic consequences rather than headline resource savings. Architectural cost analysis should make clear whether savings come from reduced work, different placement, or shifted operational responsibility.

## Evidence to use

Use customer-supplied bills and usage, resource measurements, workload models, and dated verified pricing when a real estimate is made.

## Expected report output

A cost-driver and scenario table with formulas, units, period, source dates, included costs, assumptions, sensitivity, and migration cost.

## Completion and quality checks

Do not invent current prices or customer spending. Distinguish cash savings from theoretical capacity reductions and avoid treating existing hardware or operational labor as automatically free.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
