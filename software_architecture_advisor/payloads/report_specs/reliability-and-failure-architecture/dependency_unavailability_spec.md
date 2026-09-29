# Dependency unavailability

**Section:** 10 · Reliability and failure architecture  
**Specification ID:** `AR-10-03`  
**Customer question:** What happens when an important dependency is slow, unreachable, or returns errors?

## What to include

- Select critical dependencies and define timeout, network partition, error, and prolonged unavailability scenarios.
- Explain behavior for existing work, new work, and recovery when the dependency returns.
- Assess fail-fast behavior, buffering, degraded service, fallback correctness, and operator visibility.
- Identify requirements or contracts that the current behavior fails to satisfy.

## Why this matters

Customers need more than a list of dependencies: they need to know which work stops and whether recovery creates new problems. This supports practical continuity and incident-response decisions.

## Evidence to use

Use client behavior, timeouts, queue limits, fallback logic, health checks, runbooks, and controlled failure tests or historical incidents.

## Expected report output

A dependency-outage matrix with scenario, affected workflow, user result, data consequences, degraded behavior, and recovery steps.

## Completion and quality checks

Fallback existence does not prove equivalent correctness. Distinguish transient errors from long outages and document bounded versus unbounded buffering.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
