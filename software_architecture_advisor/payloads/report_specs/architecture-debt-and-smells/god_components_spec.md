# God components

**Section:** 07 · Architecture debt and smells  
**Specification ID:** `AR-07-01`  
**Customer question:** Which components accumulate excessive responsibilities or authority?

## What to include

- Identify components that combine unrelated responsibilities, broad dependencies, and many reasons to change.
- Show responsibility groups, interfaces, state ownership, and representative change patterns.
- Explain concrete consequences for change isolation, testing, coordination, or failure impact.
- Propose candidate seams while preserving any cohesive orchestration role.

## Why this matters

The customer needs to know where concentration creates an obstacle to safe evolution. A responsibility-based diagnosis is more useful than declaring the largest file or service to be bad.

## Evidence to use

Use subsystem responsibilities, exported interfaces, dependency structure, data access, co-change, and test organization.

## Expected report output

A finding card with component, responsibility decomposition, concentration evidence, impact scenario, and smallest useful remediation.

## Completion and quality checks

Size or fan-out alone is insufficient. Distinguish a deliberate application coordinator from a component that owns unrelated domain rules and state.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
