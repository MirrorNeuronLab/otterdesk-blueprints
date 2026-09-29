# Unexpected dependencies

**Section:** 04 · Hidden coupling  
**Specification ID:** `AR-04-01`  
**Customer question:** Which components depend on one another in ways the architecture model does not explain?

## What to include

- Compare observed dependencies with documented or explicitly inferred allowed relationships.
- Identify unexpected edges and show their type, direction, implementation location, and representative path.
- Explain why the dependency is surprising and what maintenance or operational consequence it creates.
- Distinguish intentional exceptions, generated edges, and uncertain analysis results.

## Why this matters

An unexpected dependency is useful to a customer only when it changes how work should be planned. This analysis exposes shortcuts and hidden assumptions that can invalidate an apparently isolated change.

## Evidence to use

Use imports, calls, configuration references, data access, message routes, and documented boundary rules. Record the analysis tool and unsupported language features.

## Expected report output

An exception-focused dependency view plus an edge register with expectation, observation, evidence, consequence, and disposition.

## Completion and quality checks

Do not define unexpected as merely uncommon. State the baseline expectation and avoid flooding the report with unfiltered dependency edges.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
