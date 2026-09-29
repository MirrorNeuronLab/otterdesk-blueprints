# Security blast radius

**Section:** 13 · Security and trust boundaries  
**Specification ID:** `AR-13-06`  
**Customer question:** What could an attacker or unauthorized actor reach from a compromised architectural unit?

## What to include

- Define a defensive compromise scenario and the initial authority assumed, without presuming the compromise is possible.
- Trace permitted access to data, services, secrets management, administrative functions, and other tenants.
- Describe isolation boundaries, policy enforcement, and controls that limit propagation.
- Prioritize containment improvements and explicitly state unverified paths.

## Why this matters

Customers can use this analysis to reduce consequences even when individual controls fail. Scenario-based reachability makes the isolation benefit of architectural changes concrete.

## Evidence to use

Use access policies, trust boundaries, service identities, network rules, data access, and tenant isolation tests available within the authorized scope.

## Expected report output

A defensive reachability view with initial scenario, accessible capabilities, blocking controls, evidence, and containment recommendations.

## Completion and quality checks

This is not proof of exploitability or an instruction to conduct an attack. Do not assume network reachability implies authorization, and do not expose secrets in evidence excerpts.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

## Related specifications

- [Privilege concentration](../security-and-trust-boundaries/privilege_concentration_spec.md)

---

[Section contents](README.md) · [Full index](../INDEX.md)
