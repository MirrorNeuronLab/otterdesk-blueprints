# External dependencies

**Section:** 02 · Inferred system architecture  
**Specification ID:** `AR-02-04`  
**Customer question:** Which third-party or out-of-scope systems does this architecture rely on?

## What to include

- Inventory external services, libraries with architectural significance, identity providers, and infrastructure dependencies.
- Describe their role, interaction protocol, contract assumptions, and data exchanged.
- Identify availability, compatibility, ownership, portability, or cost constraints that influence the design.
- Record fallbacks, replacement difficulty, and uncertainty about the deployed version or configuration.

## Why this matters

Architectural risk often lies at a boundary the team does not control. The inventory gives customers a basis for contingency planning and for judging the real cost of a technology replacement.

## Evidence to use

Use dependency and lock files, outbound client configuration, interface schemas, deployment settings, and supplied service agreements or operational records.

## Expected report output

An external-dependency register with dependency ID, purpose, consumers, contract, data classification, criticality, fallback, and replaceability notes.

## Completion and quality checks

Distinguish runtime dependencies from build-time or development-only packages. Do not invent service guarantees, prices, support status, or current vulnerability claims.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
