# Migration stages and milestones

**Section:** 19 · Sequenced migration and refactoring roadmap  
**Specification ID:** `AR-19-01`  
**Customer question:** How can the target architecture be reached through controlled intermediate states?

## What to include

- Define the current state, selected target, and a sequence of independently reviewable migration stages.
- Describe each stage’s architecture, deliverables, entry criteria, and exit criteria.
- Identify compatibility windows, affected owners, dependencies, and validation evidence.
- Show which stages are reversible, which introduce lasting obligations, and where to reassess the plan.

## Why this matters

Customers need a path that preserves working software while it changes. Explicit intermediate states expose risks hidden by a before-and-after diagram and create opportunities to stop safely.

## Evidence to use

Use the selected option, dependency and data analyses, work breakdown, rollout constraints, and validation plan.

## Expected report output

A staged roadmap with stage IDs, resulting state, prerequisites, deliverables, validation gates, owners, and rollback notes.

## Completion and quality checks

Do not invent dates or imply all stages must ship together. Explain behavior during coexistence, not only the final state.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
