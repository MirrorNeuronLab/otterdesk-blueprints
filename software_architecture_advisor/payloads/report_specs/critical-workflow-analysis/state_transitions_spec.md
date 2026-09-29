# Workflow state transitions

**Section:** 09 · Critical workflow analysis  
**Specification ID:** `AR-09-05`  
**Customer question:** What states can the work occupy, and which transitions are valid?

## What to include

- Identify business and execution states, initial and terminal states, and transition triggers.
- Document transition preconditions, responsible component, persisted effects, and concurrency control.
- Include retries, cancellation, timeouts, compensation, and recovery transitions.
- Highlight unreachable, ambiguous, conflicting, or indefinitely nonterminal states.

## Why this matters

A state model makes correctness obligations explicit and helps customers reason about interrupted or concurrent work. It also supplies concrete targets for testing and operational visibility.

## Evidence to use

Use state fields, transition functions, event handlers, transaction boundaries, tests, and workflow records.

## Expected report output

A state-transition table or diagram with state, trigger, guard, side effect, destination, and recovery behavior.

## Completion and quality checks

Do not infer valid transitions solely from enum values. Verify the code enforcing each transition and record whether cross-process concurrency was analyzed.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
