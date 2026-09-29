# Cross-layer dependencies

**Section:** 04 · Hidden coupling  
**Specification ID:** `AR-04-06`  
**Customer question:** Where does code cross or reverse an intended architectural layer boundary?

## What to include

- Define the relevant layers and allowed dependency directions before identifying exceptions.
- Show direct and indirect cross-layer dependencies with precise source and target locations.
- Explain the impact on substitution, testing, business-rule isolation, or deployment coupling.
- Distinguish intentional composition or adapter code from a violation requiring remediation.

## Why this matters

Layer analysis is valuable when it explains why a local change leaks into unrelated concerns. An explicit rule and impact avoid treating a preferred layering style as a universal requirement.

## Evidence to use

Use dependency graph edges, architectural rules, module interfaces, tests, and composition roots. Identify whether the rule is existing policy or a proposed constraint.

## Expected report output

A layer dependency matrix and a concise exception list: rule, edge or path, evidence, consequence, and disposition.

## Completion and quality checks

Do not classify dependency injection wiring or approved adapters as violations without examining their role. Keep the diagnostic edge detail consistent with the debt section’s finding.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

## Related specifications

- [Layer violations as architectural debt](../architecture-debt-and-smells/layer_violations_spec.md)

---

[Section contents](README.md) · [Full index](../INDEX.md)
