# Ownership boundary mismatches

**Section:** 07 · Architecture debt and smells  
**Specification ID:** `AR-07-07`  
**Customer question:** Where are architectural responsibilities assigned in ways that create unresolved control or coordination?

## What to include

- Compare responsibility and data boundaries with the teams or roles accountable for changes and operation.
- Identify split authority, overlapping ownership, and unowned cross-cutting mechanisms.
- Show the change or incident process that exposes the mismatch.
- Recommend an ownership clarification, contract, or boundary adjustment and state which requires organizational approval.

## Why this matters

A technical boundary is difficult to maintain when no one can make or approve the necessary decisions. This finding helps customers resolve the governing responsibility rather than repeatedly patching symptoms.

## Evidence to use

Use team ownership records, CODEOWNERS, service catalogs, review and release practices, and supplied incident responsibilities.

## Expected report output

An ownership-debt finding with affected responsibility, current authority, mismatch, consequence, and proposed accountable role or decision.

## Completion and quality checks

Commit activity is not proof of accountability. Do not assign blame or change team responsibilities implicitly through a technical recommendation.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
