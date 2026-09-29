# Test coverage gaps

**Section:** 06 · Architecture hotspots  
**Specification ID:** `AR-06-06`  
**Customer question:** Where do important architectural behaviors lack credible verification?

## What to include

- Map critical responsibilities, contracts, workflows, and failure scenarios to existing tests.
- Distinguish execution coverage, assertion quality, contract coverage, and failure-path coverage.
- Identify untested cross-boundary behavior and areas where available coverage data is stale or absent.
- Prioritize gaps using change activity, impact, and the architectural risk being protected.

## Why this matters

A component is harder to change safely when important behavior is not checked. Architectural coverage focuses the customer on missing guarantees rather than encouraging a percentage target detached from risk.

## Evidence to use

Use test definitions, coverage artifacts, recent execution records, contract mappings, and representative assertions. Do not infer actual coverage from test filenames alone.

## Expected report output

A risk-to-test coverage matrix with behavior, existing evidence, gap, consequence, and proposed verification.

## Completion and quality checks

High line coverage does not prove correct behavior. Keep absent tests separate from tests that exist but were not run or whose results are unavailable.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
