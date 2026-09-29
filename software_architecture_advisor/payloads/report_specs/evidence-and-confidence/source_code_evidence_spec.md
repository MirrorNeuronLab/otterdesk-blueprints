# Source-code evidence

**Section:** 21 · Evidence and confidence  
**Specification ID:** `AR-21-01`  
**Customer question:** Can a reviewer locate the implementation that supports this claim?

## What to include

- Record repository identity, commit or immutable version, file path, symbol, and precise relevant line range when available.
- Include only the minimal excerpt or explanation needed to show the relevant behavior or dependency.
- Explain what the code establishes and what depends on configuration, deployment, or runtime conditions.
- Record generated code, conditional behavior, unsupported analysis, and sensitive content handling.

## Why this matters

Customers need reproducible evidence rather than a plausible description of a filename. Versioned locators let engineers verify the claim and determine whether it still applies after changes.

## Evidence to use

Use actual reviewed source artifacts and parser or analyzer outputs tied to the same snapshot. Do not manufacture line numbers from a guessed file layout.

## Expected report output

An evidence record with evidence ID, versioned locator, supporting excerpt or symbol, supported claim, scope, and limitations.

## Completion and quality checks

A code path’s existence does not prove it ran in production. Do not include secrets or unnecessary personal data, and refresh locators when the reviewed version changes.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
