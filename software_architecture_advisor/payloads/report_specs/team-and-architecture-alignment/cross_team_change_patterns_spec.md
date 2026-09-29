# Cross-team change patterns

**Section:** 15 · Team and architecture alignment  
**Specification ID:** `AR-15-04`  
**Customer question:** Which kinds of changes repeatedly require coordination across teams?

## What to include

- Select a defined history window and identify changes touching components owned by different teams.
- Describe the reason for coordination, such as shared contracts, data, release gates, or unclear responsibility.
- Show representative examples and any measured handoff or waiting time with its limitations.
- Separate essential cross-domain collaboration from avoidable architectural coordination.

## Why this matters

Customers can use actual change patterns to test whether supposedly independent boundaries reduce coordination. This makes organizational recommendations more concrete than speculation based on diagrams.

## Evidence to use

Use ownership-at-the-time mappings, pull requests, linked issues, release records, and supplied workflow timestamps. Respect private personnel information.

## Expected report output

A cross-team change table with change class, participating roles, architectural dependency, frequency basis, and candidate improvement.

## Completion and quality checks

Do not treat joint changes as inherently negative or infer wasted time from participant counts. Historical ownership changes and missing records must be reflected in the analysis.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

## Related specifications

- [Developer coordination cost](../business-impact/developer_coordination_cost_spec.md)

---

[Section contents](README.md) · [Full index](../INDEX.md)
