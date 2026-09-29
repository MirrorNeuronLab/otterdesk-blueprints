# Boundary cleanup option

**Section:** 17 · Alternative target architectures  
**Specification ID:** `AR-17-02`  
**Customer question:** What targeted boundary work would improve maintainability without wholesale restructuring?

## What to include

- Define the responsibility, interface, data, or ownership boundaries to clarify.
- Describe code movement, contract changes, state isolation, and enforcement rules needed.
- Explain expected effects on change isolation, testing, coordination, and deployment where relevant.
- Provide a staged path, effort assumptions, residual limitations, and validation measures.

## Why this matters

Customers need an intermediate option between small fixes and a major redesign. Boundary cleanup can be evaluated on whether it removes specific dependencies rather than on architectural fashion.

## Evidence to use

Use boundary findings, hidden coupling, responsibility maps, state ownership, and representative change scenarios.

## Expected report output

An option card with current and proposed boundaries, affected components, staged work, expected outcomes, cost basis, and risks.

## Completion and quality checks

Do not promise independent deployment unless runtime, contract, and data dependencies support it. Specify which forms of separation the option actually improves.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
