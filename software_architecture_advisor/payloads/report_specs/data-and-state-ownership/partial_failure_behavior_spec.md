# Partial-failure behavior of state

**Section:** 08 · Data and state ownership  
**Specification ID:** `AR-08-08`  
**Customer question:** What happens when only part of a multi-step state change succeeds?

## What to include

- Trace important state-changing workflows across stores, services, and external side effects.
- Enumerate failure windows before and after writes, acknowledgements, and message publication.
- Describe detection, retries, compensation, deduplication, and reconciliation for each window.
- Identify stranded work, duplicate effects, violated invariants, and manual repair requirements.

## Why this matters

A successful-path diagram can conceal the most consequential correctness risks. Customers need failure-window analysis to judge whether retries and migrations are safe for important business operations.

## Evidence to use

Use write ordering, transaction and messaging code, recovery jobs, integration tests, and relevant incident sequences.

## Expected report output

A failure-window table containing step, completed effects, possible failure, resulting state, recovery action, and unresolved risk.

## Completion and quality checks

Do not claim atomicity across independent systems without a demonstrated mechanism. Keep state consequences here linked to the broader reliability findings rather than duplicating them inconsistently.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

## Related specifications

- [State inconsistency risks](../reliability-and-failure-architecture/state_inconsistency_risks_spec.md)
- [Retry and idempotency behavior](../critical-workflow-analysis/retry_and_idempotency_behavior_spec.md)

---

[Section contents](README.md) · [Full index](../INDEX.md)
