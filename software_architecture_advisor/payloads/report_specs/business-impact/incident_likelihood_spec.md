# Incident likelihood

**Section:** 20 · Business impact  
**Specification ID:** `AR-20-03`  
**Customer question:** What does the available evidence say about architectural contributors to incident risk?

## What to include

- Define the incident class, exposure, observation period, and relevant architectural mechanism.
- Separate observed incident frequency from forward-looking probability or qualitative risk.
- Identify recurring mechanisms, containment weaknesses, and limitations in incident detection or classification.
- Describe the change intended to reduce risk and the evidence needed to evaluate its effect.

## Why this matters

Customers need realistic reliability prioritization without false precision. This aspect keeps a plausible architectural failure scenario from being presented as a measured prediction.

## Evidence to use

Use supplied incident records, root-cause evidence, deployment and workload exposure, reliability findings, and verified mitigations.

## Expected report output

An incident-risk assessment with defined event class, evidence window, exposure basis, mechanism, uncertainty, and proposed risk-reduction measure.

## Completion and quality checks

Static architecture analysis cannot by itself establish incident probability. Avoid percentages unless a defensible model and data support them, and do not treat no recorded incidents as proof of no risk.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

## Related specifications

- [Failure cascades](../reliability-and-failure-architecture/failure_cascades_spec.md)

---

[Section contents](README.md) · [Full index](../INDEX.md)
