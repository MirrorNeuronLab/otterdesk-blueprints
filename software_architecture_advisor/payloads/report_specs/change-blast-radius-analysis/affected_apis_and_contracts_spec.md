# Affected APIs and contracts

**Section:** 05 · Change blast-radius analysis  
**Specification ID:** `AR-05-04`  
**Customer question:** Which public or internal contracts could change for consumers?

## What to include

- Identify affected endpoints, callable interfaces, events, message schemas, and behavior guarantees.
- Describe compatibility at the syntax, semantic, error-handling, and versioning levels.
- List known consumers and deployment or release ordering obligations.
- Specify required contract tests, deprecation steps, or migration communication.

## Why this matters

Customers need to know whether a change can be shipped independently. Contract analysis makes consumer obligations and compatibility risks explicit before implementation or rollout.

## Evidence to use

Use interface definitions, producer-consumer implementations, contract tests, schema history, and known client inventories. State gaps in external consumer visibility.

## Expected report output

A contract-change matrix with contract ID, old and proposed behavior, consumer impact, compatibility status, and rollout requirement.

## Completion and quality checks

A schema-compatible change can still alter meaning or timing. Do not promise backward compatibility without checking the relevant consumer expectations.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
