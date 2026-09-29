# Architecture drift

**Section:** 07 · Architecture debt and smells  
**Specification ID:** `AR-07-09`  
**Customer question:** Where has implementation moved away from an agreed or previously observed architecture?

## What to include

- Identify the reference architecture, policy, or baseline version and its authority.
- Show deviations in boundaries, dependencies, responsibilities, deployment shape, or data ownership.
- Distinguish intentional evolution from undocumented deviation and stale documentation.
- Assess consequence and propose restoring the rule, revising the design, or recording an approved exception.

## Why this matters

Drift matters when the team’s mental model and enforcement no longer match reality. A customer needs to know whether to fix the code, update the architecture, or deliberately accept a tradeoff.

## Evidence to use

Use design records, architecture rules, baseline and current graphs, deployment definitions, and change history.

## Expected report output

A drift register with baseline, observed change, evidence, intent status, consequence, and proposed disposition.

## Completion and quality checks

Do not assume the older design is better. Record uncertainty about intent and link trend claims to comparable versions rather than a single current snapshot.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

## Related specifications

- [Architecture diff between releases](../architecture-evolution/architecture_diff_between_releases_spec.md)

---

[Section contents](README.md) · [Full index](../INDEX.md)
