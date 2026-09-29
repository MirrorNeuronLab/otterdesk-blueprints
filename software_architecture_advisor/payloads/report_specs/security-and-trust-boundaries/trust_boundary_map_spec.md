# Trust boundary map

**Section:** 13 · Security and trust boundaries  
**Specification ID:** `AR-13-01`  
**Customer question:** Where does the system accept data or actions from an actor with a different trust level?

## What to include

- Identify users, services, tenants, administrators, external systems, and execution environments in the reviewed scope.
- Mark trust transitions for requests, messages, data, configuration, and administrative operations.
- Describe validation, identity, authorization, isolation, and transport controls at each transition.
- Record assumptions, bypass paths, and boundaries not visible in the available evidence.

## Why this matters

Customers need to see where trust changes, not just where network lines are drawn. This supports decisions about isolation and defense placement across the actual workflows.

## Evidence to use

Use routing, gateway and identity configuration, middleware, access policies, topology, and sensitive workflow paths.

## Expected report output

A trust-boundary view and register with actors, transition, data or action, controls, evidence status, and open questions.

## Completion and quality checks

Do not equate internal network location with trust. Do not claim a complete penetration test, compliance assessment, or absence of vulnerabilities from this review.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
