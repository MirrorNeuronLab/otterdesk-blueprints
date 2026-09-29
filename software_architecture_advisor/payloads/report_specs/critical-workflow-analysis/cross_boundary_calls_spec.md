# Cross-boundary calls

**Section:** 09 · Critical workflow analysis  
**Specification ID:** `AR-09-04`  
**Customer question:** Which workflow steps cross a boundary that adds coordination or operational obligations?

## What to include

- Mark process, service, team, trust, and data-ownership boundaries on the workflow.
- Describe request or event contracts, sync or async semantics, and transferred data.
- Record timeout, authentication, compatibility, and transaction assumptions at each boundary.
- Identify repeated or unnecessary crossings and explain their practical consequence.

## Why this matters

Not every call has the same architectural cost. Boundary-aware analysis helps customers see where a workflow depends on independent availability, releases, ownership, or trust decisions.

## Evidence to use

Use the topology and ownership models, call sites, client configuration, interface definitions, and traces.

## Expected report output

A boundary-crossing table aligned to workflow steps with boundary type, contract, obligations, evidence, and improvement candidate.

## Completion and quality checks

Do not equate a source-level function call with a network hop. Verify actual placement and distinguish potential crossings from observed runtime interactions.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
