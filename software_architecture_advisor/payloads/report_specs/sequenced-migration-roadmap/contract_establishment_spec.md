# Contract establishment

**Section:** 19 · Sequenced migration and refactoring roadmap  
**Specification ID:** `AR-19-02`  
**Customer question:** What explicit contracts must exist before moving responsibilities?

## What to include

- Identify APIs, events, data ownership rules, invariants, and compatibility promises needed at the proposed seam.
- Specify producer and consumer responsibilities, versioning, error semantics, and validation.
- Describe adapters or compatibility layers needed to preserve current behavior.
- Define contract tests and approval conditions before dependent migration stages begin.

## Why this matters

A migration is easier to control when the boundary is explicit before implementations move. Customers can verify compatibility at the seam instead of relying on coordinated knowledge of internal details.

## Evidence to use

Use existing consumer behavior, implicit-contract findings, domain rules, interface schemas, and relevant tests.

## Expected report output

A contract-establishment work stage with contract inventory, compatibility strategy, test evidence, owners, and exit gate.

## Completion and quality checks

Do not treat an interface signature as the whole contract. Include behavior, state, timing assumptions where required, and clarify which promises remain provisional.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
