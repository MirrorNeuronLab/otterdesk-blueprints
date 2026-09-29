# Architectural constraints

**Section:** 23 · Implementation-ready work packages  
**Specification ID:** `AR-23-03`  
**Customer question:** What properties and boundaries must the implementation preserve?

## What to include

- Specify required compatibility, dependency directions, ownership, state invariants, and service guarantees.
- Include security, privacy, deployment, resource, and operational constraints relevant to the task.
- Define permitted interfaces and prohibited shortcuts, with a reason for each.
- Link every important constraint to an enforcement method, test, or review condition.

## Why this matters

A task can satisfy a local goal while damaging the larger architecture. Explicit constraints give the implementer the boundaries needed to avoid introducing new hidden coupling or weakening required behavior.

## Evidence to use

Use approved architecture rules, customer requirements, contracts, data ownership, trust boundaries, and preserved strengths.

## Expected report output

A constraint list with ID, requirement, rationale, source, permitted exception process, and verification method.

## Completion and quality checks

Do not introduce new architectural policy without labeling it proposed. Resolve conflicting constraints before implementation and specify when human review is required.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
