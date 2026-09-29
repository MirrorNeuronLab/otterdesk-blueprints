# Team-to-service boundary alignment

**Section:** 15 · Team and architecture alignment  
**Specification ID:** `AR-15-03`  
**Customer question:** Do technical units match the responsibilities teams can actually own independently?

## What to include

- Compare service, module, data, and deployment boundaries with team accountability.
- Identify many-team components, single-team ownership spread across tightly coupled services, and cross-team shared state.
- Explain effects on decision authority, release coordination, incident response, and prioritization.
- Compare technical boundary changes with ownership or interface agreements.

## Why this matters

Customers need to know whether friction comes from code structure, organizational responsibility, or both. The answer can prevent an unnecessary technical rewrite when a clearer ownership agreement would suffice.

## Evidence to use

Use architecture maps, ownership matrices, data authority, release dependencies, and representative coordination examples.

## Expected report output

A team-by-component matrix with significant mismatches, consequence, alternative remedies, and decisions requiring confirmation.

## Completion and quality checks

Do not assume one team per service is universally optimal. Account for team size, specialization, shared platforms, and the customer’s operating model.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
