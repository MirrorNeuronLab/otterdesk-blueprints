# Layer violations as architectural debt

**Section:** 07 · Architecture debt and smells  
**Specification ID:** `AR-07-03`  
**Customer question:** Which layer-rule exceptions create a meaningful maintenance obligation?

## What to include

- Reference the defined layer model and verified exceptions from cross-layer dependency analysis.
- Explain the practical cost of each significant violation, including testing and substitution limitations.
- Separate temporary exceptions, intentional adapters, and unmanaged erosion.
- Propose enforcement or refactoring and identify migration prerequisites.

## Why this matters

Customers benefit from knowing which rule violations matter and how to prevent recurrence. This turns a rule-checking result into an improvement decision rather than a style-compliance exercise.

## Evidence to use

Use cross-layer dependency finding IDs, policy or design records, tests, and representative changes.

## Expected report output

A debt record containing rule, exception, mechanism of harm, intended disposition, proposed control, and completion condition.

## Completion and quality checks

Do not invent a layer policy and then present its violations as breaches of an existing agreement. Explain the expected benefit of a proposed policy.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

## Related specifications

- [Cross-layer dependencies](../hidden-coupling/cross_layer_dependencies_spec.md)

---

[Section contents](README.md) · [Full index](../INDEX.md)
