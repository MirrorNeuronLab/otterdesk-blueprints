# What the system does

**Section:** 01 · Executive architecture brief  
**Specification ID:** `AR-01-01`  
**Customer question:** What business work does this system perform, for whom, and where does its responsibility end?

## What to include

- Describe the business purpose, primary users, and the outcomes they expect, using customer-facing language.
- Identify the principal inputs, outputs, and business capabilities; distinguish the product from supporting infrastructure.
- State the system boundary, important external actors, and capabilities explicitly outside the review scope.
- Connect the description to two or three representative user journeys or operational workflows.

## Why this matters

This gives every later architectural finding a business context. Without a shared statement of purpose, readers cannot judge whether complexity is necessary or whether a recommendation protects the work the system exists to do.

## Evidence to use

Use product documentation, reviewed requirements, public interfaces, entry points, and representative workflows. Reconcile disagreements between documentation and implementation rather than silently choosing one.

## Expected report output

A short plain-language narrative plus a compact capability table: capability, user, input, output, and responsible subsystem.

## Completion and quality checks

A non-specialist should be able to explain the system after reading this. Do not substitute a technology list, repository description, or speculative business objective for its purpose.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
