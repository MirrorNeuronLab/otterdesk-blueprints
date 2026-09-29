# Independent deployment

**Section:** 20 · Business impact  
**Specification ID:** `AR-20-08`  
**Customer question:** How much release autonomy do teams or services actually have?

## What to include

- Define the deployment unit and the form of independence relevant to the customer.
- Identify synchronized releases, contract dependencies, shared migrations, and common release gates.
- Explain the impact on release frequency, coordination, rollback, and ownership.
- Describe changes that would improve autonomy and the evidence needed to demonstrate it.

## Why this matters

Customers often create service boundaries to gain delivery autonomy. This aspect checks whether that benefit exists and whether proposed improvements remove the real release dependencies.

## Evidence to use

Use deployment pipelines, release histories, compatibility rules, schema migrations, ownership, and microservice-independence findings.

## Expected report output

A deployment-autonomy assessment with unit, current obligations, observed constraints, improvement option, and success criterion.

## Completion and quality checks

Separate independently deployable code from safe independent operation. Do not claim a release is autonomous when consumer or schema changes still require coordinated timing.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
