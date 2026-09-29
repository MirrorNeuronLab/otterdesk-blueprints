# Authentication and authorization boundaries

**Section:** 13 · Security and trust boundaries  
**Specification ID:** `AR-13-04`  
**Customer question:** Where are identity and permission decisions made and enforced?

## What to include

- Separate authentication, authorization, tenant isolation, and administrative access decisions.
- Map enforcement across gateways, services, background jobs, data stores, and external integrations.
- Explain identity propagation, delegated authority, object-level checks, and failure behavior.
- Identify gaps, duplicated decisions, and reliance on upstream checks that downstream paths can bypass.

## Why this matters

Customers need confidence that a valid identity does not automatically obtain inappropriate access. Mapping enforcement reveals whether security depends on one entry path while alternate workflows use weaker controls.

## Evidence to use

Use middleware, policy evaluation, route registration, identity configuration, service-to-service credentials, and positive and negative authorization tests.

## Expected report output

An access-control boundary matrix with actor, resource, decision point, enforcement point, propagated identity, and verification.

## Completion and quality checks

Do not infer authorization merely from authentication middleware. Treat missing evidence as a gap to verify rather than proof of an exploitable vulnerability.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
