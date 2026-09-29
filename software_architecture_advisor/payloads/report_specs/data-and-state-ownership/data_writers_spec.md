# Data writers

**Section:** 08 · Data and state ownership  
**Specification ID:** `AR-08-02`  
**Customer question:** Which actors can create, update, or delete important state?

## What to include

- List write-capable components, jobs, migrations, administrative tools, and external integrations.
- Describe allowed operations, entry points, validation, and transaction boundaries.
- Identify multiple writers and the mechanism that coordinates ordering, conflicts, and invariants.
- Distinguish configured permission from observed or implemented write behavior.

## Why this matters

A complete writer inventory is essential for migration and consistency decisions. An overlooked background job or administrative path can invalidate a supposedly isolated schema or ownership change.

## Evidence to use

Use code-level writes, query builders, stored procedures, access policies, migration scripts, and available audit evidence.

## Expected report output

A writer matrix with entity, writer, operation, interface, validation, transaction scope, and coordination rule.

## Completion and quality checks

Record dynamic or out-of-repository writers as visibility gaps. Do not claim exclusive ownership merely because only one writer was found in the reviewed repository.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
