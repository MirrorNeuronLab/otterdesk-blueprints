# Affected services and deployments

**Section:** 05 · Change blast-radius analysis  
**Specification ID:** `AR-05-07`  
**Customer question:** Which operational units must change, restart, or coordinate a release?

## What to include

- Map affected code and contracts to services, workers, scheduled jobs, images, and deployment units.
- Identify configuration, infrastructure, permission, and data migration changes.
- Describe required rollout order, mixed-version windows, and rollback coordination.
- List operational owners, observation points, and environments needing validation.

## Why this matters

Code impact and deployment impact are different. This view gives customers a realistic release plan and surfaces coordination that would be missed by a repository-only dependency analysis.

## Evidence to use

Use build mappings, deployment manifests, release pipelines, interface compatibility, and environment configuration. Clearly label unverified live topology.

## Expected report output

A deployment-impact table: unit, required action, dependency, release order, compatibility window, owner status, and rollback consideration.

## Completion and quality checks

Do not assume one repository produces one deployment unit. Separate recommended deployment actions from changes proven necessary by the scenario.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
