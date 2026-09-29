# Hidden workflow dependencies

**Section:** 09 · Critical workflow analysis  
**Specification ID:** `AR-09-07`  
**Customer question:** What must be true outside the explicit workflow graph for it to succeed?

## What to include

- Identify prerequisites involving configuration, time, cache warmth, background jobs, operator actions, or external state.
- Show where the workflow relies on each prerequisite and how the reliance is enforced or assumed.
- Describe consequences of stale, missing, or incorrectly ordered prerequisite work.
- Recommend explicit checks, contracts, orchestration, or observability where needed.

## Why this matters

A workflow can look self-contained while depending on work that nobody sees in its diagram. Making these prerequisites explicit helps customers reproduce failures and plan reliable execution or migration.

## Evidence to use

Use configuration reads, readiness checks, scheduled tasks, shared-state access, runbooks, tests, and relevant failure history.

## Expected report output

A prerequisite register with dependency, owning actor, evidence, required condition, failure consequence, and proposed enforcement.

## Completion and quality checks

Do not invent environmental requirements from intuition. Mark inferred prerequisites and specify the observation or experiment needed to verify them.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
