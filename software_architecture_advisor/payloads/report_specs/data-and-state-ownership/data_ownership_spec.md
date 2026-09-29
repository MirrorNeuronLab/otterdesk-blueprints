# Data ownership

**Section:** 08 · Data and state ownership  
**Specification ID:** `AR-08-01`  
**Customer question:** Who has authority over each important data entity and its rules?

## What to include

- Inventory business entities and operational state with stable identifiers and clear scope.
- Identify the component and accountable role that define the schema, lifecycle, and invariants.
- Distinguish logical ownership, physical storage, stewardship, and permission to access.
- Flag disputed, split, or absent ownership and the changes that require a decision.

## Why this matters

Clear data authority anchors service boundaries and prevents incompatible changes by different consumers. The customer needs to know who can safely change a model, not just which database stores it.

## Evidence to use

Use schema and migration ownership, write paths, domain documentation, permissions, and confirmed team responsibilities.

## Expected report output

A data-ownership register with entity, logical owner, storage location, invariant authority, accountable role, and unresolved questions.

## Completion and quality checks

Do not equate the database administrator or most frequent committer with the domain owner. Unknown ownership must remain explicit.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
