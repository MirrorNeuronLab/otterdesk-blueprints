# Workload relocation

**Section:** 16 · Decision and what-if analysis  
**Specification ID:** `AR-16-04`  
**Customer question:** What changes if this work moves to another service, process, host, or environment?

## What to include

- Define the workload, current placement, target placement, and intended benefit.
- Map required code, models or binaries where applicable, state, configuration, credentials, and network access.
- Assess data movement, latency, resource fit, scheduling, recovery, and trust-boundary changes.
- Describe rollout, comparison testing, fallback, and remaining dependencies on the original environment.

## Why this matters

Customers need to see whether relocation changes more than execution location. This scenario is especially useful for evaluating isolation, local versus remote execution, or independent scaling without overlooking state and control requirements.

## Evidence to use

Use deployment topology, workflow and data-flow analysis, resource measurements, access policies, and runtime configuration.

## Expected report output

A placement comparison with dependencies, resource assumptions, changed boundaries, operational obligations, validation, and rollback.

## Completion and quality checks

Do not assume a workload is portable because it runs in a container. Label unmeasured latency and resource estimates and identify external services still required after relocation.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
