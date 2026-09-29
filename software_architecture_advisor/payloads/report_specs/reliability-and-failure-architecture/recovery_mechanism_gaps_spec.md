# Recovery mechanism gaps

**Section:** 10 · Reliability and failure architecture  
**Specification ID:** `AR-10-06`  
**Customer question:** Where does the architecture lack a workable path back to a correct operating state?

## What to include

- Inventory required recovery scenarios and existing automated or manual mechanisms.
- Identify missing detection, repair, replay, reconciliation, backup restoration, or ownership steps.
- Compare recovery behavior with supplied recovery objectives and operational constraints.
- Recommend a specific recovery capability, runbook, or test with measurable completion criteria.

## Why this matters

A system can detect failure yet have no reliable way to repair its effects. A gap-focused recovery plan helps customers reduce uncertainty about restoration rather than equating backup existence with recoverability.

## Evidence to use

Use runbooks, backup and restoration configuration, repair tooling, replay mechanisms, and actual recovery exercises or incident records.

## Expected report output

A recovery coverage matrix with failure scenario, detection, recovery owner, mechanism, verified result, objective gap, and action.

## Completion and quality checks

Do not infer tested recovery times or data-loss bounds. Keep configured objectives, estimated capability, and measured recovery results clearly separate.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

## Related specifications

- [Next measurements and verification tasks](../unknowns-and-verification-tasks/next_measurements_and_verification_tasks_spec.md)

---

[Section contents](README.md) · [Full index](../INDEX.md)
