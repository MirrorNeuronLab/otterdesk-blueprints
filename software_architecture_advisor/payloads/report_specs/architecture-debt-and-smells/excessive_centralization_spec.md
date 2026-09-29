# Excessive centralization

**Section:** 07 · Architecture debt and smells  
**Specification ID:** `AR-07-04`  
**Customer question:** Where does centralized control or state impose an avoidable system-wide constraint?

## What to include

- Identify central coordinators, registries, databases, deployment gates, and shared decision points.
- Describe the concentration of throughput, authority, knowledge, or failure exposure.
- Explain why the concentration is harmful under a specific change or operating scenario.
- Compare decentralization with simpler alternatives such as isolation, replication, or reduced coupling.

## Why this matters

Centralization can be intentional and beneficial. The report should help the customer decide where it has become an actual constraint rather than promoting distribution as a default goal.

## Evidence to use

Use dependency structure, topology, ownership, resource observations, workflows, and incident or release evidence.

## Expected report output

A concentration finding with central role, affected dependents, constraint scenario, supporting evidence, alternatives, and tradeoffs.

## Completion and quality checks

A central component is not automatically a single point of failure or a bottleneck. Verify redundancy and load characteristics before making those claims.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
