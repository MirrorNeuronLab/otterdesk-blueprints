# Effort estimate

**Section:** 18 · Concrete prioritized recommendations  
**Specification ID:** `AR-18-05`  
**Customer question:** What work and uncertainty determine the likely implementation effort?

## What to include

- Break effort into design, code, tests, data migration, operations, coordination, and rollout.
- Use ranges or defined qualitative bands, with assumptions about scope, skills, tooling, and availability.
- Identify uncertain work, dependencies, and prerequisites that could materially change the estimate.
- Separate engineering effort from elapsed time and ongoing operational cost.

## Why this matters

Customers need realistic tradeoffs when prioritizing architecture work. An explained estimate is more useful than a confident number that ignores migration, validation, and organizational coordination.

## Evidence to use

Use the proposed work breakdown, repository and deployment scope, team-supplied estimates, historical analogues, and unresolved implementation questions.

## Expected report output

An effort breakdown with range or band definitions, assumptions, excluded work, confidence, and factors that would change the estimate.

## Completion and quality checks

Do not convert lines of code directly into person-days or promise calendar dates without planning inputs. Clearly label estimates as estimates rather than delivery commitments.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

## Related specifications

- [Infrastructure cost](../business-impact/infrastructure_cost_spec.md)

---

[Section contents](README.md) · [Full index](../INDEX.md)
