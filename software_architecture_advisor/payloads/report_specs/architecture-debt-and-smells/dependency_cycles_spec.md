# Dependency cycles as architectural debt

**Section:** 07 · Architecture debt and smells  
**Specification ID:** `AR-07-02`  
**Customer question:** Which dependency cycles create enough ongoing cost to justify intervention?

## What to include

- Reference verified cycle evidence from hidden-coupling analysis rather than independently duplicating the graph.
- Identify which cycles cross intended ownership, build, service, or deployment boundaries.
- Describe the recurring cost and the constraint that prevents independent change.
- Compare cycle-breaking options, effort, risks, and reasons an intentional cycle might remain.

## Why this matters

Detection alone does not establish a remediation priority. This aspect converts a structural observation into a decision about whether the cycle’s cost exceeds the cost and risk of breaking it.

## Evidence to use

Use cycle IDs, dependency paths, build or initialization failures, change examples, and boundary rules.

## Expected report output

A debt finding linked to the cycle register, with consequence, remediation alternatives, priority rationale, and validation target.

## Completion and quality checks

Keep technical edge evidence in the canonical cycle analysis. Do not count the same strongly connected group as many independent debt items.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

## Related specifications

- [Circular dependencies](../hidden-coupling/circular_dependencies_spec.md)

---

[Section contents](README.md) · [Full index](../INDEX.md)
