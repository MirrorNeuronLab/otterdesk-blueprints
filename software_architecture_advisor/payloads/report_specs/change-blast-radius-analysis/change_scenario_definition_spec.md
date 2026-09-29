# Change scenario definition

**Section:** 05 · Change blast-radius analysis  
**Specification ID:** `AR-05-01`  
**Customer question:** Exactly what change are we evaluating, and what counts as an impact?

## What to include

- Specify the target component, interface, data entity, or behavior and the proposed change type.
- State compatibility assumptions, affected environments, baseline version, and intended rollout shape.
- Define impact categories such as compile failure, behavioral change, schema incompatibility, rollout coordination, and operational effects.
- List exclusions and missing inputs that constrain the analysis.

## Why this matters

Blast radius is meaningful only relative to a change. A precise scenario prevents every reachable dependency from being presented as something that will break.

## Evidence to use

Use the proposed diff, design request, API or schema change, relevant architecture model, and supplied rollout constraints. Where no concrete change exists, label the scenario hypothetical.

## Expected report output

A scenario header with scenario ID, baseline, target, change description, assumptions, impact definitions, and scope.

## Completion and quality checks

Separate compatibility-preserving edits from contract changes. Every downstream result must refer to this scenario and distinguish possible exposure from demonstrated impact.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
