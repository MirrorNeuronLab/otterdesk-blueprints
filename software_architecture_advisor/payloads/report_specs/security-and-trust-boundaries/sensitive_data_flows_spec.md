# Sensitive-data flows

**Section:** 13 · Security and trust boundaries  
**Specification ID:** `AR-13-03`  
**Customer question:** Where does sensitive information enter, move, persist, and leave the architecture?

## What to include

- Use customer-approved data classifications or clearly labeled provisional categories.
- Trace sensitive fields through APIs, storage, queues, caches, logs, exports, and external services.
- Describe access control, minimization, retention, encryption, and redaction mechanisms evidenced at each stage.
- Identify unnecessary copies, unclear retention, or uncontrolled boundary crossings.

## Why this matters

Customers need to understand where confidentiality assumptions depend on architecture. This view supports decisions about local processing, third-party exposure, and data handling without relying on a generic privacy claim.

## Evidence to use

Use schemas, transformations, logging and telemetry code, storage settings, outbound clients, and supplied handling requirements. Do not reproduce real sensitive values.

## Expected report output

A classified data-flow map with data category, source, transformation, destination, protection, retention basis, and verification gap.

## Completion and quality checks

Code may not show deployed encryption or retention behavior. Do not assert legal compliance or data residency guarantees without the required operational and policy evidence.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
