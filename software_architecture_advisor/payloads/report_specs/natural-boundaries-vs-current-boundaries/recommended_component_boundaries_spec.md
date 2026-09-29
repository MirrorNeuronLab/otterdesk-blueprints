# Recommended component boundaries

**Section:** 03 · Natural boundaries versus current boundaries  
**Specification ID:** `AR-03-01`  
**Customer question:** Where would boundaries better match responsibilities and independent change?

## What to include

- Propose candidate boundaries using responsibility cohesion, data ownership, interfaces, and change patterns.
- Compare each candidate with the current organization and name the affected components.
- Describe what would move, what would remain shared, and the contract between the proposed sides.
- List expected benefits, counterarguments, and the evidence needed before committing.

## Why this matters

The purpose is to help customers make change safer and ownership clearer, not to maximize the number of modules or services. Explicit comparisons turn a vague redesign idea into a reviewable hypothesis.

## Evidence to use

Use subsystem responsibilities, dependency structure, data access, historical co-change, and domain input. Treat algorithmic clusters as supporting signals rather than semantic truth.

## Expected report output

A current-versus-proposed boundary view and candidate table with rationale, affected responsibilities, expected benefit, costs, and validation needs.

## Completion and quality checks

Do not describe a proposed boundary as objectively natural. Include a keep-current option and distinguish module separation from service extraction.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
