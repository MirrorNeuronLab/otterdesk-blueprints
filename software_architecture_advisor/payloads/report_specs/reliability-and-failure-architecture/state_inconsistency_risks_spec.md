# State inconsistency risks

**Section:** 10 · Reliability and failure architecture  
**Specification ID:** `AR-10-04`  
**Customer question:** Which failures can leave the system believing mutually incompatible things?

## What to include

- Select important invariants and link them to the stores, services, and side effects involved.
- Construct failure sequences that could violate those invariants, including concurrent or reordered work.
- Describe detection, reconciliation, compensation, and customer-visible consequences.
- Prioritize risks by impact and evidence while distinguishing tolerated divergence from corruption.

## Why this matters

Availability alone is not sufficient when recovery can leave incorrect state. This aspect makes the customer’s correctness obligations visible in reliability decisions.

## Evidence to use

Use the data consistency and partial-failure analyses, transaction and messaging implementation, reconciliation procedures, and targeted tests.

## Expected report output

A reliability risk register linked to canonical data findings, with invariant, failure sequence, consequence, recovery, and verification.

## Completion and quality checks

Do not duplicate inconsistent descriptions across sections. Avoid claiming a theoretical sequence has occurred unless operational evidence supports that claim.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

## Related specifications

- [Consistency and disagreement](../data-and-state-ownership/consistency_and_disagreement_spec.md)
- [Partial-failure behavior of state](../data-and-state-ownership/partial_failure_behavior_spec.md)

---

[Section contents](README.md) · [Full index](../INDEX.md)
