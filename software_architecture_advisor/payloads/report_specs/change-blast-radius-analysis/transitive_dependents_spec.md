# Transitive dependents

**Section:** 05 · Change blast-radius analysis  
**Specification ID:** `AR-05-03`  
**Customer question:** How could this change propagate beyond immediate consumers?

## What to include

- Trace relevant multi-hop dependency paths from the changed target to downstream components or user-facing capabilities.
- Show the propagation mechanism at each hop rather than listing graph reachability alone.
- State traversal depth, stop conditions, compatibility barriers, and excluded edge types.
- Group shared paths and identify distant impacts that deserve targeted validation.

## Why this matters

Transitive analysis reveals surprises that a local code review can miss. Explaining the propagation mechanism keeps the result useful instead of expanding into an indiscriminate list of everything in the system.

## Evidence to use

Use a versioned typed graph, contract semantics, data lineage, workflows, and available test or trace evidence. Preserve uncertainty for inferred edges.

## Expected report output

A focused impact subgraph and path table containing path, propagation rationale, impact category, confidence, and validation action.

## Completion and quality checks

Do not equate reachability with certain impact. Report truncation and graph coverage; a missing edge is not proof that no dependency exists.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
