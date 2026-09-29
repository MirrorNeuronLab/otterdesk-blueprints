# Direct dependents

**Section:** 05 · Change blast-radius analysis  
**Specification ID:** `AR-05-02`  
**Customer question:** Which immediate consumers need review for this change?

## What to include

- List immediate callers, importers, subscribers, data consumers, and configuration dependents relevant to the scenario.
- Identify the exact contract or behavior each consumer relies on.
- Classify each consumer as unaffected, potentially affected, confirmed affected, or unresolved with a reason.
- Link affected consumers to code locations, owners where known, and validation actions.

## Why this matters

Direct dependents provide the first practical review and test list. Contract-aware classification avoids overwhelming customers with consumers that are connected but not affected by the proposed change.

## Evidence to use

Use typed dependency edges, interface usage, schema references, configuration, and representative tests or traces at the analyzed version.

## Expected report output

A direct-impact table: consumer, dependency type, relied-on contract, impact status, explanation, evidence, and check.

## Completion and quality checks

A dependency edge alone establishes exposure, not breakage. Report unresolved dynamic consumers and out-of-repository consumers explicitly.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
