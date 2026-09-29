# Coding-agent handoff

**Section:** 23 · Implementation-ready work packages  
**Specification ID:** `AR-23-08`  
**Customer question:** Can a coding agent execute this bounded task without guessing the intent or its authority?

## What to include

- Bundle the goal, context, constraints, non-goals, steps, tests, and acceptance criteria with stable references.
- State the baseline, allowed tools and working area, approval status, and prohibited actions.
- Define stop-and-escalate conditions for missing evidence, incompatible code, scope expansion, risky data changes, or failed validation.
- Specify the required completion report: changes, reasoning summary, executed checks, results, unresolved risks, and next approval.

## Why this matters

Customers need delegated implementation to remain bounded, inspectable, and reversible where possible. A complete handoff reduces the chance that an agent fills gaps with invented assumptions or performs unauthorized operational changes.

## Evidence to use

Use all work-package fields, actual repository context, approved permissions, and the linked evidence and decision records.

## Expected report output

A self-contained task brief with resolvable links and an explicit execution-and-reporting contract for a human or agent.

## Completion and quality checks

Do not equate generated instructions with authorization. Require human approval for deployment, destructive changes, secrets handling, or material scope expansion unless separately and explicitly authorized.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

## Related specifications

- [Architectural constraints](../implementation-ready-work-packages/architectural_constraints_spec.md)
- [Acceptance criteria](../implementation-ready-work-packages/acceptance_criteria_spec.md)

---

[Section contents](README.md) · [Full index](../INDEX.md)
