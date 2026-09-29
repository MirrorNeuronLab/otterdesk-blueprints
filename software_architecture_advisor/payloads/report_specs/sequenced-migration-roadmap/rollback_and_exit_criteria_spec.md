# Rollback and exit criteria

**Section:** 19 · Sequenced migration and refactoring roadmap  
**Specification ID:** `AR-19-08`  
**Customer question:** When should the migration stop, reverse, or be considered complete?

## What to include

- Define stage-specific success, pause, abort, rollback, and forward-repair conditions.
- State what can be reversed in code, configuration, routing, and data, and identify irreversible transitions.
- Describe recovery ownership, required backups or reconciliation, and compatibility during reversal.
- Specify final cleanup, evidence retention, and removal of temporary mechanisms.

## Why this matters

Customers need a controlled response when a migration behaves differently from expectations. Exit criteria also prevent temporary dual systems and compatibility code from becoming permanent accidental architecture.

## Evidence to use

Use migration stages, validation metrics, data semantics, recovery mechanisms, and customer-approved risk thresholds.

## Expected report output

A gate and recovery table with stage, success condition, abort signal, rollback or repair action, owner, and completion evidence.

## Completion and quality checks

Do not call a migration reversible merely because a deployment can be reverted. Include data and external effects, and distinguish proposed thresholds from approved operational limits.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

## Related specifications

- [Migration steps within a work package](../implementation-ready-work-packages/migration_steps_spec.md)
- [Recovery mechanism gaps](../reliability-and-failure-architecture/recovery_mechanism_gaps_spec.md)

---

[Section contents](README.md) · [Full index](../INDEX.md)
