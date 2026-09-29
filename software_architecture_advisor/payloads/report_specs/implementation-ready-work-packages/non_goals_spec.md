# Non-goals

**Section:** 23 · Implementation-ready work packages  
**Specification ID:** `AR-23-04`  
**Customer question:** What work should explicitly not be included in this task?

## What to include

- Name adjacent refactors, behavior changes, technology replacements, and cleanup that are outside scope.
- Identify files, interfaces, data, or environments that must not be changed except through separate approval.
- Explain intentional limitations and residual issues deferred to later work packages.
- State how the implementer should handle a newly discovered dependency that requires scope expansion.

## Why this matters

Customers need predictable change boundaries, especially when delegating to coding agents. Non-goals prevent a narrow architectural improvement from expanding into an unreviewable redesign.

## Evidence to use

Use the selected option, staged roadmap, priority decisions, task goal, and customer-authorized scope.

## Expected report output

A non-goal and exclusion block with deferred work links, protected surfaces, reasons, and escalation conditions.

## Completion and quality checks

Do not use non-goals to omit work necessary for correctness without flagging the conflict. If the goal cannot be met inside scope, the task must stop for a decision rather than quietly expand.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
