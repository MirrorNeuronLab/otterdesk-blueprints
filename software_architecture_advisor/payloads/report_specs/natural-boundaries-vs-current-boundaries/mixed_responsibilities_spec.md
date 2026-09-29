# Mixed responsibilities

**Section:** 03 · Natural boundaries versus current boundaries  
**Specification ID:** `AR-03-02`  
**Customer question:** Which components combine concerns that should change or be governed separately?

## What to include

- Identify components that implement distinct business capabilities or mix domain, orchestration, storage, and presentation concerns.
- Show the specific interfaces, code regions, data, and change reasons associated with each responsibility.
- Explain the practical consequence of the mixture, such as unrelated releases or difficult testing.
- Suggest the smallest useful separation and any intentional orchestration that should remain together.

## Why this matters

Mixed responsibilities matter when they impose unnecessary coordination or make local changes unsafe. Explaining the mechanism helps customers distinguish harmful entanglement from a useful, cohesive coordinator.

## Evidence to use

Use exported APIs, execution paths, state access, tests, ownership, and commit examples. Do not rely on file length or class size alone.

## Expected report output

A responsibility decomposition table: component, distinct concerns, evidence, consequence, candidate separation, and retained integration point.

## Completion and quality checks

Each candidate needs more than a naming or size heuristic. Account for cases where transactions or business invariants justify keeping responsibilities together.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
