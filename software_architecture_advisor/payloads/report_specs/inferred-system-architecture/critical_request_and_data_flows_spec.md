# Critical request and data flows

**Section:** 02 · Inferred system architecture  
**Specification ID:** `AR-02-05`  
**Customer question:** How do important requests and data travel across the system?

## What to include

- Select flows that represent core customer journeys or important operational work.
- Trace entry points, validation, domain processing, asynchronous hops, state access, and externally visible results.
- Show synchronous versus asynchronous edges, data transformations, and the boundaries crossed.
- Record alternate paths, missing observations, and the source supporting each significant edge.

## Why this matters

A flow view turns a static component inventory into an explanation of behavior. It also anchors later blast-radius, latency, reliability, and data-ownership analysis in work customers recognize.

## Evidence to use

Use code paths, routing configuration, message schemas, integration tests, and available correlated runtime traces. Indicate which branches are observed and which are inferred.

## Expected report output

A small number of annotated sequence or flow views with a numbered narrative and links to components, data entities, and evidence.

## Completion and quality checks

Do not present one observed trace as proof of all possible behavior. Include asynchronous completion and externally visible failure outcomes when applicable.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
