# Missing runtime information

**Section:** 22 · Unknowns and verification tasks  
**Specification ID:** `AR-22-02`  
**Customer question:** What operational evidence is needed to validate the static architecture model?

## What to include

- List missing topology, workload, trace, resource, queue, error, deployment, or recovery observations.
- Connect each missing input to a specific claim that cannot yet be validated.
- Describe the required environment, time window, workload conditions, and minimally necessary data.
- Specify collection constraints, redaction, access ownership, and non-production alternatives where appropriate.

## Why this matters

Customers can avoid collecting large amounts of telemetry without a clear question. A targeted request identifies what is necessary to verify capacity, failure, and deployment conclusions.

## Evidence to use

Use gaps identified by topology, latency, scalability, workflow, and reliability analyses. Respect the customer’s operational and privacy constraints.

## Expected report output

A runtime evidence request table with input, purpose, collection scope, responsible role, handling requirements, and decision unlocked.

## Completion and quality checks

Do not imply missing runtime information is already accessible or measured. Prefer minimal, authorized collection and do not recommend disruptive production experiments without explicit approval.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
