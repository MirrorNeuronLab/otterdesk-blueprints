# Migration steps within a work package

**Section:** 23 · Implementation-ready work packages  
**Specification ID:** `AR-23-05`  
**Customer question:** What sequence should the implementer follow to reach the task goal safely?

## What to include

- Break the task into ordered changes with prerequisites, affected artifacts, and expected intermediate behavior.
- Include compatibility, state transitions, configuration, validation, and cleanup relevant to this task.
- Mark steps that can occur locally versus those requiring deployment, production access, or human approval.
- Specify rollback or forward-repair conditions at consequential steps.

## Why this matters

A task-level sequence connects the high-level roadmap to executable work. Customers can review intermediate states and prevent implementation choices that bypass required safety or compatibility gates.

## Evidence to use

Use the linked migration stage, actual code and data dependencies, contracts, and required validation.

## Expected report output

An ordered task procedure with inputs, action, expected result, check, authorization boundary, and recovery note for each step.

## Completion and quality checks

Do not substitute invented shell commands for validated instructions. Separate planning from execution, and never interpret a work package as automatic permission to deploy or modify production data.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
