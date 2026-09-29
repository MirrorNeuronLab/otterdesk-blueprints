# Technical debt trends

**Section:** 14 · Architecture evolution  
**Specification ID:** `AR-14-05`  
**Customer question:** Is the architecture’s unresolved maintenance burden increasing, decreasing, or changing form?

## What to include

- Track a stable register of architectural findings with open, accepted, mitigated, resolved, and unverified states.
- Compare additions, closures, reappearances, and changes in impact or affected scope.
- Show remediation evidence and separate removed symptoms from eliminated causes.
- Describe important tradeoffs, including new complexity introduced by improvements.

## Why this matters

Customers need a way to judge whether architecture work is producing durable progress. A finding-based trend is more interpretable than a single opaque debt score.

## Evidence to use

Use dated report findings, code and architecture changes, validation results, accepted exceptions, and relevant operational outcomes.

## Expected report output

A debt trend summary with finding IDs, status transitions, evidence of improvement, residual risks, and new obligations.

## Completion and quality checks

Do not convert findings into monetary debt without an explicit model. Keep accepted risk visible and avoid counting a renamed or moved issue as resolved.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
