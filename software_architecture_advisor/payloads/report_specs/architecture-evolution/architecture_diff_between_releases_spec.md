# Architecture diff between releases

**Section:** 14 · Architecture evolution  
**Specification ID:** `AR-14-06`  
**Customer question:** What changed architecturally between two specific releases?

## What to include

- Identify exact baseline and target commits or release artifacts and the repositories included.
- Compare components, interfaces, dependency edges, ownership, state, workflows, and deployment topology.
- Separate additions, removals, modifications, and renames and explain behaviorally significant changes.
- Highlight new risks, resolved findings, compatibility implications, and validation gaps.

## Why this matters

An architecture diff helps customers review the consequences of a release without reading every code change. It also makes improvements and newly introduced coupling auditable.

## Evidence to use

Use reproducible snapshots, semantic component mappings, source and manifest diffs, schema changes, and available before/after operational evidence.

## Expected report output

A release comparison with a concise change narrative, focused before/after views, changed contracts, and linked findings.

## Completion and quality checks

Do not compare unmatched environments or missing repositories as though they were equivalent. Treat renamed components carefully and distinguish intended deployment changes from observed production changes.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
