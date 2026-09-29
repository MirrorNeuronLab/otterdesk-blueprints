# End-to-end workflow

**Section:** 09 · Critical workflow analysis  
**Specification ID:** `AR-09-01`  
**Customer question:** How does an important customer or operational task complete?

## What to include

- Define the workflow trigger, actors, preconditions, business outcome, and completion condition.
- Trace the main path through validation, domain decisions, queues, workers, state, and external effects.
- Include significant alternative, cancellation, and failure paths rather than only success.
- Identify components, data entities, contracts, and evidence for the steps.

## Why this matters

A workflow is a concrete unit customers can recognize and evaluate. It provides the common reference for assessing latency, reliability, ownership, and the consequences of an architectural change.

## Evidence to use

Use routing and orchestration code, message handlers, state transitions, integration tests, and correlated traces when available.

## Expected report output

A numbered sequence or activity view and narrative with trigger, steps, boundaries, completion, alternative outcomes, and evidence status.

## Completion and quality checks

Do not define completion as merely accepting a request when work finishes asynchronously. Mark inferred branches and any missing systems in the end-to-end path.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
