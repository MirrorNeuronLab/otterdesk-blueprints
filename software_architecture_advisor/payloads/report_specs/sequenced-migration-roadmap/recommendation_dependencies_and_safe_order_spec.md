# Recommendation dependencies and safe order

**Section:** 19 · Sequenced migration and refactoring roadmap  
**Specification ID:** `AR-19-07`  
**Customer question:** Which actions must precede others, and which can safely proceed in parallel?

## What to include

- Model prerequisites between recommendation and migration-stage IDs.
- Explain the dependency type: contract, data, code, deployment, organizational decision, or validation.
- Identify mutually exclusive alternatives, shared prerequisites, and work that can run independently.
- Show blocked stages and the smallest action that would unblock them.

## Why this matters

Customers need to avoid starting a seemingly valuable refactor before its safety conditions exist. An explicit dependency model also reveals opportunities for parallel work and removes ambiguity from sequencing.

## Evidence to use

Use selected recommendations, compatibility rules, state authority transitions, validation gates, and confirmed ownership decisions.

## Expected report output

A dependency table or small directed graph with stage IDs, prerequisite rationale, blocker status, and safe parallel groups.

## Completion and quality checks

Do not equate a numbered list with proven safe ordering. Resolve dependency cycles or describe an intentional combined stage, and keep calendar estimates separate from logical order.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
