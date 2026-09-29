# Component elimination

**Section:** 16 · Decision and what-if analysis  
**Specification ID:** `AR-16-05`  
**Customer question:** What would break or need to move if we removed this component?

## What to include

- Define the removal candidate and why it appears unnecessary or replaceable.
- Inventory consumers, unique responsibilities, state, scheduled work, and operational or compliance-related dependencies supplied by the customer.
- Distinguish responsibilities that disappear from those that must move or be replaced.
- Describe deprecation, observation, traffic or data migration, archival, and rollback conditions.

## Why this matters

Customers can simplify architecture only when they understand the obligations a component still fulfills. Removal analysis protects against deleting infrequent but important background or recovery behavior.

## Evidence to use

Use inbound dependencies, workflow participation, runtime activity windows, data ownership, job schedules, and operational procedures.

## Expected report output

A removal impact brief with retained obligations, affected consumers, replacement or deletion plan, verification window, and exit criteria.

## Completion and quality checks

No recent traffic is not proof of no value. Account for seasonal jobs, disaster recovery, manual operations, and external consumers that may be outside the observation window.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
