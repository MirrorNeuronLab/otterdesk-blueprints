# Implicit contracts

**Section:** 04 · Hidden coupling  
**Specification ID:** `AR-04-05`  
**Customer question:** What unstated expectations must remain true for components to cooperate?

## What to include

- Identify assumptions about schemas, field meaning, naming, ordering, timing, error behavior, and version compatibility.
- Name both the producer and consumer of each assumption and the location where it is relied upon.
- Describe the change that would violate the assumption and the observable consequence.
- Recommend contract documentation, validation, compatibility checks, or explicit interfaces where appropriate.

## Why this matters

An undocumented contract can be broken by a change that looks locally correct. Making it explicit creates something the team can test, review, and preserve during a migration.

## Evidence to use

Use paired producer-consumer code, serializers, parsers, fixtures, integration tests, and historical compatibility failures. Keep speculative assumptions separate from demonstrated reliance.

## Expected report output

An implicit-contract register with producer, consumer, assumption, evidence, breaking-change example, and proposed enforcement.

## Completion and quality checks

Do not label every implementation detail a contract. Demonstrate that another component relies on it, or state that consumer evidence is still missing.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
