# Microservice independence

**Section:** 16 · Decision and what-if analysis  
**Specification ID:** `AR-16-06`  
**Customer question:** In what ways is this microservice actually independent, and in what ways is it not?

## What to include

- Assess independent development, testing, deployment, scaling, failure containment, data ownership, and decision authority separately.
- Identify shared schemas, synchronized releases, internal contract reliance, and required runtime availability.
- Show concrete scenarios that demonstrate or challenge each form of independence.
- Recommend retaining, strengthening, redefining, or merging the boundary based on the intended benefit.

## Why this matters

Customers need a more precise answer than whether a component is called a microservice. Independence is multidimensional, and improvements should target the specific capability the boundary is intended to provide.

## Evidence to use

Use build and release configuration, contracts, state ownership, failure behavior, change history, and team accountability.

## Expected report output

An independence matrix with dimension, evidence, current constraint, business significance, and proposed action.

## Completion and quality checks

Do not reduce independence to one opaque score. A service can scale independently while still needing coordinated data migrations or releases.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

## Related specifications

- [Independent deployment](../business-impact/independent_deployment_spec.md)

---

[Section contents](README.md) · [Full index](../INDEX.md)
