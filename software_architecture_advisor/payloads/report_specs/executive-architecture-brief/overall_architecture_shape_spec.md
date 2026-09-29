# Overall architecture shape

**Section:** 01 · Executive architecture brief  
**Specification ID:** `AR-01-02`  
**Customer question:** How is the system organized, and which architectural choices define how it operates?

## What to include

- Describe the observed architectural style or combination of styles without forcing a single label.
- Identify the main execution units, communication patterns, and state stores.
- Explain which boundaries are source-code boundaries, process boundaries, and independent deployment boundaries.
- Summarize the most consequential design choices and distinguish observed structure from documented intent.

## Why this matters

Readers need a compact mental model before they can interpret detailed risks. The shape also establishes whether a proposed change is local, cross-process, or operationally disruptive.

## Evidence to use

Use entry points, build targets, deployment manifests, interface definitions, dependency analysis, and available runtime traces. Treat naming conventions as clues rather than proof.

## Expected report output

A one-page architecture overview with a small component view, a legend for boundary types, and a brief explanation of the dominant interaction and state patterns.

## Completion and quality checks

Do not equate the number of repositories with the number of services. Mark inferred runtime behavior and show where production topology has not been verified.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
