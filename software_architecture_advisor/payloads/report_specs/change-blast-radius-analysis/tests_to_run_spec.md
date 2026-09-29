# Tests to run

**Section:** 05 · Change blast-radius analysis  
**Specification ID:** `AR-05-06`  
**Customer question:** Which tests provide useful evidence that this change is safe?

## What to include

- Map impacted contracts and workflows to existing unit, integration, contract, end-to-end, and operational tests.
- Explain why each selected test or suite is relevant to the change scenario.
- Identify gaps that require new tests, manual verification, or runtime observation.
- State execution prerequisites, expected outcomes, and limits of the proposed test selection.

## Why this matters

An actionable test plan turns blast-radius analysis into a practical release decision. The rationale helps customers balance confidence with the cost of running every available test.

## Evidence to use

Use test definitions, available coverage mappings, historical failures, contract ownership, and execution configuration. Distinguish discovered tests from tests actually executed.

## Expected report output

A test-impact table with test identifier or validated command, covered risk, prerequisite, expected result, and execution status.

## Completion and quality checks

Do not claim safety solely because selected tests pass. Do not invent runnable commands or imply tests were executed when they were only recommended.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

## Related specifications

- [Required tests](../implementation-ready-work-packages/required_tests_spec.md)

---

[Section contents](README.md) · [Full index](../INDEX.md)
