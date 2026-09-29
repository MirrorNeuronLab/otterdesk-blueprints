# Safe module extraction

**Section:** 16 · Decision and what-if analysis  
**Specification ID:** `AR-16-02`  
**Customer question:** Can this module be extracted without breaking its consumers or hidden obligations?

## What to include

- Define the extraction target, destination, intended interface, and behaviors that must remain unchanged.
- Inventory inbound and outbound dependencies, shared state, initialization, and configuration requirements.
- Identify prerequisite cleanup, compatibility adapters, and test coverage needed to establish a seam.
- Describe a staged extraction, rollback approach, and proof that the old and new paths meet the same contract.

## Why this matters

Customers need a concrete feasibility assessment rather than reassurance that moving files is straightforward. The analysis exposes the work required to make the extracted unit genuinely usable outside its current context.

## Evidence to use

Use dependency slices, exported symbols, build configuration, state access, workflow tests, and change-impact findings.

## Expected report output

An extraction feasibility card with seam, dependencies, blockers, migration stages, validation, and residual coupling.

## Completion and quality checks

Do not claim safe extraction from passing unit tests alone. Check runtime configuration, side effects, packaging, and consumers outside the immediate repository when visible.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

## Related specifications

- [Service extraction and cutover](../sequenced-migration-roadmap/service_extraction_and_cutover_spec.md)

---

[Section contents](README.md) · [Full index](../INDEX.md)
