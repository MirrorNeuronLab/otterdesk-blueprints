# Major subsystems and responsibilities

**Section:** 02 · Inferred system architecture  
**Specification ID:** `AR-02-01`  
**Customer question:** What are the main functional parts, and what work is each responsible for?

## What to include

- Identify subsystems around coherent business or operational responsibilities rather than folders alone.
- List their main capabilities, public interfaces, state, and critical dependencies.
- Map each subsystem to repositories, packages, processes, and deployment units as applicable.
- Record ambiguous responsibilities, overlap, and responsibilities that appear to have no clear owner.

## Why this matters

A responsibility map helps readers navigate the system and evaluate whether later findings concern a meaningful architectural unit. It also provides a shared vocabulary for change planning and ownership discussions.

## Evidence to use

Use entry points, exported interfaces, call and import relationships, data access, build configuration, and representative execution paths.

## Expected report output

A subsystem inventory with stable component IDs, responsibilities, implementation locations, interfaces, state, and confidence.

## Completion and quality checks

Each major capability should map to an identified subsystem or an explicit unknown. Avoid claiming semantic cohesion solely from package names.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
