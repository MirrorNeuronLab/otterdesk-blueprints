# Leaky abstractions

**Section:** 07 · Architecture debt and smells  
**Specification ID:** `AR-07-05`  
**Customer question:** Where must consumers understand details that an interface is meant to hide?

## What to include

- Identify interfaces whose consumers rely on internal storage, vendor behavior, ordering, or representation.
- Show the abstraction’s intended promise and the specific consumer code that bypasses or compensates for it.
- Describe changes that would leak across the interface and the resulting coordination or testing burden.
- Recommend a clearer contract, a better boundary, or a narrower promise where appropriate.

## Why this matters

An abstraction that hides names but not obligations can give customers a false sense of replaceability. Concrete leakage examples show whether the boundary actually reduces change cost.

## Evidence to use

Use paired interface and consumer implementations, error handling, data conversions, tests, and replacement or upgrade history.

## Expected report output

A leakage register: abstraction, promised separation, leaked detail, consumer reliance, consequence, and proposed remedy.

## Completion and quality checks

Some constraints must be exposed intentionally. Do not demand an abstraction that conceals essential domain behavior or merely moves complexity elsewhere.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
