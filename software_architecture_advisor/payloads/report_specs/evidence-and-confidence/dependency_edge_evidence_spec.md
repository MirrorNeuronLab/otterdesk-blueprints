# Dependency-edge evidence

**Section:** 21 · Evidence and confidence  
**Specification ID:** `AR-21-03`  
**Customer question:** What does each important edge mean, and where did it come from?

## What to include

- Define graph version, node identities, granularity, edge direction, and edge type.
- Attach provenance such as import location, call site, schema access, configuration reference, or observed trace.
- Distinguish static, dynamically inferred, configured, and observed relationships.
- Record confidence, analysis coverage, unsupported constructs, and edge normalization or deduplication rules.

## Why this matters

Customers cannot interpret a dependency graph reliably when all lines mean different things. Typed, sourced edges support defensible cycles, impact paths, and boundary findings.

## Evidence to use

Use analyzer outputs and underlying code or runtime artifacts. Preserve a reproducible extraction method and tool version where applicable.

## Expected report output

An edge evidence record or export with source, target, type, direction, provenance, graph snapshot, and limitations.

## Completion and quality checks

An import, runtime call, data dependency, and historical co-change are not interchangeable edges. Do not count inferred and observed representations of one relationship as independent corroboration.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
