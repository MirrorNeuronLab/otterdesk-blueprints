# Circular dependencies

**Section:** 04 · Hidden coupling  
**Specification ID:** `AR-04-02`  
**Customer question:** Which components form dependency cycles, and how do those cycles constrain change?

## What to include

- Find cycles in a clearly defined graph, such as imports, service calls, or data dependencies.
- List cycle members and show a representative closed path with source evidence.
- Explain effects on build order, initialization, testing, ownership, or coordinated change where supported.
- Identify candidate cycle-breaking seams and intentional feedback loops that should not be treated as defects.

## Why this matters

Cycle detection shows where components cannot be reasoned about independently in the chosen dependency model. Explaining the consequence helps customers prioritize significant cycles rather than merely count them.

## Evidence to use

Use a versioned dependency graph with edge semantics and source locations. Validate representative edges, especially dynamic or generated ones.

## Expected report output

A cycle register with graph type, members, representative path, affected boundaries, practical impact, and candidate break points.

## Completion and quality checks

A static dependency cycle does not prove a runtime deadlock. Group overlapping cycles into understandable components rather than enumerating every equivalent path.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

## Related specifications

- [Dependency cycles as architectural debt](../architecture-debt-and-smells/dependency_cycles_spec.md)

---

[Section contents](README.md) · [Full index](../INDEX.md)
