# Merge candidates

**Section:** 03 · Natural boundaries versus current boundaries  
**Specification ID:** `AR-03-03`  
**Customer question:** Which separated components create overhead without meaningful independence?

## What to include

- Identify components that repeatedly coordinate releases, share ownership and state, or communicate excessively.
- Explain what independence the existing boundary provides and whether that benefit is actually used.
- Describe a possible merge at the code, process, or deployment level without assuming all three must merge.
- Assess benefits, new concentration risks, and reasons to preserve the boundary.

## Why this matters

Architecture improvement is not always decomposition. A merge can be worth considering when separation creates substantial operational and coordination work without supporting an important requirement.

## Evidence to use

Use release history, synchronous call patterns, shared-schema usage, ownership information, and deployment configuration. Corroborate apparent coupling with actual workflows.

## Expected report output

A merge-candidate comparison with present boundary value, current overhead, proposed scope, expected simplification, and risks.

## Completion and quality checks

High communication alone is not sufficient. Consider security, scaling, fault isolation, organizational constraints, and future requirements before recommending a merge.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
