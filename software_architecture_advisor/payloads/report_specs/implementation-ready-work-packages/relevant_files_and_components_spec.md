# Relevant files and components

**Section:** 23 · Implementation-ready work packages  
**Specification ID:** `AR-23-02`  
**Customer question:** Where should the implementer look, and which adjacent areas could be affected?

## What to include

- List actual repositories, baseline commits, files, symbols, components, contracts, and data entities relevant to the task.
- Explain the role of each item and distinguish likely edit targets from read-only context or validation targets.
- Include consumers, tests, deployment configuration, and operational artifacts implicated by the change.
- Record incomplete mappings and require revalidation when the baseline has changed.

## Why this matters

Customers need work packages that reduce navigation cost without hiding dependencies. A role-labeled file map helps an implementer begin efficiently and recognize when the task’s assumptions no longer match the code.

## Evidence to use

Use versioned source evidence, dependency and blast-radius findings, contract definitions, and migration stages.

## Expected report output

A task context table with artifact path or locator, version, component, relevance, permitted action, and related impact.

## Completion and quality checks

Do not invent filenames or promise the listed files are exhaustive. Treat a stale baseline or missing artifact as a re-scoping condition rather than silently adapting the architecture.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
