# CRUD and ownership matrix

**Section:** 08 · Data and state ownership  
**Specification ID:** `AR-08-09`  
**Customer question:** Can we see data authority and access patterns in one actionable view?

## What to include

- Create a matrix of important entities against components or actors, showing create, read, update, and delete access.
- Overlay logical ownership, authoritative source, access interface, and direct versus mediated access.
- Highlight multiple writers, unauthorized or unexpected paths, and ownership gaps.
- Link each significant cell to evidence and record unknown or only permission-based access separately.

## Why this matters

The matrix condenses several analyses into a reviewable artifact. It makes boundary leaks and migration obligations visible without requiring the customer to interpret a dense general-purpose graph.

## Evidence to use

Reconcile the ownership, writer, reader, source-of-truth, and access-path inventories in this section.

## Expected report output

A legend-equipped CRUD matrix plus a short exception list and links to the detailed data registers.

## Completion and quality checks

Differentiate implemented operations, configured permissions, and observed access. Do not leave a blank cell ambiguous between no access and not analyzed.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

## Related specifications

- [State isolation](../sequenced-migration-roadmap/state_isolation_spec.md)

---

[Section contents](README.md) · [Full index](../INDEX.md)
