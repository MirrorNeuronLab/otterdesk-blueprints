# Privilege concentration

**Section:** 13 · Security and trust boundaries  
**Specification ID:** `AR-13-02`  
**Customer question:** Which identities or components hold authority far broader than their normal responsibilities?

## What to include

- Inventory significant service identities, administrative roles, tokens, and shared credentials by role without exposing secret values.
- Map permissions to required capabilities and identify broadly shared or overpowered authority.
- Explain the consequences of misuse or compromise under a scoped scenario.
- Recommend narrower roles, separation of duties, or credential boundaries where justified.

## Why this matters

Privilege concentration can enlarge the consequence of a local error or compromise. A customer needs a responsibility-to-permission comparison to decide where reduced authority is practical.

## Evidence to use

Use supplied access policies, role bindings, application authorization, deployment identity settings, and service responsibility mappings.

## Expected report output

A privilege matrix with identity class, granted scope, required responsibility, concentration concern, evidence, and proposed reduction.

## Completion and quality checks

Do not include credentials or sensitive token contents in the report. Configured access is not proof of actual use, and required operational access may need separate confirmation.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
