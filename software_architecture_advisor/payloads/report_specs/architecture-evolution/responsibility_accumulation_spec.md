# Responsibility accumulation

**Section:** 14 · Architecture evolution  
**Specification ID:** `AR-14-04`  
**Customer question:** Which components are steadily acquiring unrelated roles?

## What to include

- Track additions to public interfaces, owned data, workflow participation, and dependencies over selected versions.
- Group changes by responsibility rather than only counting files or lines.
- Identify expansion into distinct domains or cross-cutting functions and the resulting change obligations.
- Assess whether consolidation remains coherent or suggests a future decomposition seam.

## Why this matters

Customers can address responsibility concentration earlier when its trajectory is visible. This view distinguishes healthy product growth from a component becoming the default destination for unrelated work.

## Evidence to use

Use interface and schema history, release diffs, component responsibilities, pull-request descriptions, and representative workflows.

## Expected report output

A responsibility timeline with component, added role, evidence, related dependencies, consequence, and candidate response.

## Completion and quality checks

Increasing code size is not equivalent to accumulating unrelated responsibilities. Preserve domain context and label inferred responsibility classifications.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
