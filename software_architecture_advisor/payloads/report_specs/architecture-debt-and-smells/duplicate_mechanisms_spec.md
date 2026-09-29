# Duplicate mechanisms

**Section:** 07 · Architecture debt and smells  
**Specification ID:** `AR-07-06`  
**Customer question:** Where do multiple implementations solve the same architectural problem inconsistently?

## What to include

- Identify parallel mechanisms for configuration, retries, authorization, scheduling, serialization, or other cross-cutting behavior.
- Compare their responsibilities, contracts, semantics, and important differences.
- Explain duplicated maintenance, inconsistent behavior, or integration risk with concrete examples.
- Assess consolidation, shared contracts, or justified separation without assuming all duplication should disappear.

## Why this matters

Customers care when parallel mechanisms create repeated work or conflicting guarantees. The comparison helps distinguish harmful duplication from independent implementations with genuinely different requirements.

## Evidence to use

Use implementation paths, configuration, interface semantics, tests, and maintenance history. Similar names or source text are only discovery signals.

## Expected report output

A mechanism comparison table with consumers, behavior differences, maintenance consequence, consolidation option, and migration risk.

## Completion and quality checks

Do not recommend a universal shared framework without accounting for coupling and ownership costs. Identify semantic differences that a consolidation must preserve.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
