# Production criticality

**Section:** 06 · Architecture hotspots  
**Specification ID:** `AR-06-04`  
**Customer question:** Which components support the outcomes the customer can least afford to lose?

## What to include

- Map components to business-critical workflows, users, data, and operational obligations.
- Describe consequences of unavailability, incorrect results, delayed processing, or data loss.
- Record supplied service objectives, recovery expectations, and criticality owners.
- Separate stakeholder-declared criticality, observed usage, and reviewer inference.

## Why this matters

A hotspot should reflect the importance of the work at risk, not only the structure of the code. This makes prioritization relevant to the customer’s operations and business commitments.

## Evidence to use

Use reviewed business requirements, workflow mappings, supplied service objectives, operational metrics, and incident records. Ask for verification tasks when business impact is unknown.

## Expected report output

A criticality matrix: component, supported capability, failure consequence, requirement, evidence basis, and owner status.

## Completion and quality checks

Do not infer revenue, legal obligations, or customer importance from names or traffic alone. Keep business criticality separate from the probability that a component fails.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
