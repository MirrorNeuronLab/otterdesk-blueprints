# Code ownership

**Section:** 15 · Team and architecture alignment  
**Specification ID:** `AR-15-01`  
**Customer question:** Who maintains and reviews each important part of the implementation?

## What to include

- Map declared code owners, maintainers, review rules, and contribution patterns to architectural components.
- Separate formal accountability from recent edit activity and historical expertise.
- Identify unclear ownership, review bottlenecks, and areas lacking sufficient knowledge distribution.
- Record the source date and verification status of ownership information.

## Why this matters

Customers need to know who can review or carry out an architectural change. A careful ownership map reduces the risk of assigning work based on a misleading author count.

## Evidence to use

Use CODEOWNERS, maintainer files, service catalogs, review history, and confirmed team records. Use contribution history only as a qualified signal.

## Expected report output

A component ownership table with declared owner, reviewer role, contribution evidence, coverage gap, and confirmation needed.

## Completion and quality checks

Do not infer performance, competence, or blame from commit patterns. Do not present an inferred contributor as the accountable owner without confirmation.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
