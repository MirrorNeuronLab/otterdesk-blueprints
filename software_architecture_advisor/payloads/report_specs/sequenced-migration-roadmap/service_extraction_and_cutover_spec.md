# Service extraction and cutover

**Section:** 19 · Sequenced migration and refactoring roadmap  
**Specification ID:** `AR-19-06`  
**Customer question:** How will the prepared boundary become an independently operated unit?

## What to include

- Define packaging, runtime, configuration, identity, networking, and deployment requirements for the extracted unit.
- Specify traffic or work routing, readiness checks, observability, and mixed-version compatibility.
- Plan ownership transfer, rollout gates, decommissioning, and documentation updates.
- Describe fallback and recovery for the unit and the surrounding workflow during cutover.

## Why this matters

Service extraction creates operational responsibilities beyond moving code. Customers need those responsibilities in the roadmap so that the new boundary works during real deployment and failure conditions.

## Evidence to use

Use the extraction scenario, contracts, state migration plan, deployment topology, and operational requirements.

## Expected report output

A cutover stage with deployment checklist, routing sequence, operational owner, verification evidence, fallback, and decommissioning criteria.

## Completion and quality checks

Only include service extraction when it is part of the selected option. Do not imply the new service is independent until data, release, and recovery obligations are addressed.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
