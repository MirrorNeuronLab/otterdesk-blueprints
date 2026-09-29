# Change lead time

**Section:** 20 · Business impact  
**Specification ID:** `AR-20-01`  
**Customer question:** How does the architecture influence the time needed to deliver a meaningful change?

## What to include

- Define the change class and the start and end events used for lead time.
- Separate implementation, review, testing, coordination, deployment, and waiting where data permits.
- Connect specific architectural dependencies or verification burdens to observed delays or testable hypotheses.
- Describe the expected effect of a recommendation and how it would be measured against a baseline.

## Why this matters

Customers need to understand whether architecture work can help delivery rather than merely improve code appearance. A mechanism-linked view avoids attributing all delay to architecture when other factors may dominate.

## Evidence to use

Use supplied issue, pull-request, build, test, and deployment timestamps, representative changes, and architecture dependencies.

## Expected report output

A lead-time impact brief with metric definition, sample and period, observed components of delay, architectural mechanism, and validation plan.

## Completion and quality checks

Do not claim causality from timing correlation alone. Label estimated time savings and account for change size, staffing, process changes, and missing records.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
