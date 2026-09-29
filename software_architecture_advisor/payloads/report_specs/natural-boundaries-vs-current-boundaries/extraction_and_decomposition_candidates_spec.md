# Extraction and decomposition candidates

**Section:** 03 · Natural boundaries versus current boundaries  
**Specification ID:** `AR-03-04`  
**Customer question:** What can be separated safely, and what prevents separation today?

## What to include

- Identify cohesive capabilities that could become modules, libraries, workers, or services.
- Inventory inbound and outbound contracts, state dependencies, and transactional assumptions.
- Describe the candidate seam, prerequisite cleanup, and incremental extraction strategy.
- Compare the intended gain with added operational, testing, and consistency complexity.

## Why this matters

Customers need feasible extraction seams rather than an instruction to split a large component. A prerequisite-aware assessment helps avoid moving existing coupling across a network boundary.

## Evidence to use

Use dependency slices, public APIs, data ownership, workflow traces, tests, and release coupling. Add domain review where capability boundaries are uncertain.

## Expected report output

An extraction candidate card containing scope, seam, contracts, owned data, blockers, target form, staged approach, and validation conditions.

## Completion and quality checks

Do not recommend a separate service merely because code can be moved. Identify transaction and compatibility issues before declaring the candidate independently deployable.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
