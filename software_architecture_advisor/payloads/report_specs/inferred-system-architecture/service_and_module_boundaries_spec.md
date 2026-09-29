# Service and module boundaries

**Section:** 02 · Inferred system architecture  
**Specification ID:** `AR-02-02`  
**Customer question:** Where are the actual separation points, and how strong are those boundaries?

## What to include

- Identify module, package, service, process, and deployment boundaries separately.
- Describe the contracts and allowed interactions across each boundary.
- Show shared state, cross-boundary imports, and coordinated deployment requirements that weaken independence.
- Compare documented boundaries with those enforced by implementation and build or deployment rules.

## Why this matters

A named service is not necessarily an independent unit. Boundary analysis lets the customer judge whether work can be changed, tested, owned, or released separately.

## Evidence to use

Use dependency edges, interface schemas, access rules, database permissions, build targets, deployment definitions, and release history where available.

## Expected report output

A boundary register or matrix: boundary, type, contract, enforcement, shared dependencies, independence limitations, and evidence.

## Completion and quality checks

State the kind of independence being assessed. An independently built module may still require coordinated data changes or release sequencing.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
