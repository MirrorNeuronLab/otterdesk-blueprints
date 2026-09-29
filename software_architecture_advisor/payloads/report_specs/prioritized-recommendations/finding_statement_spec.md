# Finding statement

**Section:** 18 · Concrete prioritized recommendations  
**Specification ID:** `AR-18-01`  
**Customer question:** What exactly is wrong or worth improving, and under what conditions?

## What to include

- Assign a stable finding ID and write a concise, specific statement about the affected architecture.
- Describe current behavior or structure, the expected property, and the gap between them.
- Name the components, boundary, workflow, or state involved and the triggering scenario.
- Separate observation from interpretation and keep distinct causes in separate findings where useful.

## Why this matters

Customers cannot act on a vague statement such as improve modularity. A precise finding gives evidence, impact, and remediation a shared target and prevents the recommendation from drifting into generic advice.

## Evidence to use

Use verified structural or behavioral observations and an explicit requirement, invariant, or stated design objective.

## Expected report output

A finding header with ID, title, scoped statement, affected entities, scenario, status, and confidence reference.

## Completion and quality checks

Avoid unsupported adjectives such as fragile or unscalable. State the actual mechanism and do not disguise a preferred design style as a demonstrated defect.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
