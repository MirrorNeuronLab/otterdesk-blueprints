# Dependency and security exposure

**Section:** 13 · Security and trust boundaries  
**Specification ID:** `AR-13-05`  
**Customer question:** Which dependencies or architectural interfaces expand the security exposure under review?

## What to include

- Inventory exposed interfaces, high-privilege integrations, executable dependency paths, and supply-chain inputs relevant to architecture.
- Distinguish deployed runtime components from development-only or unused dependencies.
- Relate supplied security findings to reachable functionality and configuration rather than repeating unfiltered alerts.
- Record source dates, version certainty, compensating controls, and required follow-up assessment.

## Why this matters

Customers need an architecture-aware interpretation of exposure. It helps prioritize investigation where a dependency’s role and privileges make an issue consequential.

## Evidence to use

Use lock files, software inventories, build and deployment configuration, exposed routes, and supplied or separately verified dated security assessments.

## Expected report output

An exposure register with dependency or interface, version basis, deployment role, reachability, authority, dated evidence, and next action.

## Completion and quality checks

Do not invent current vulnerabilities or claim an advisory applies without version and configuration evidence. A dependency inventory is not a vulnerability assessment or security guarantee.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
