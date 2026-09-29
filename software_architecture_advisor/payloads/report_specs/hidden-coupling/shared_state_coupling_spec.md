# Shared-state coupling

**Section:** 04 · Hidden coupling  
**Specification ID:** `AR-04-04`  
**Customer question:** Which components influence one another through state rather than explicit interfaces?

## What to include

- Inventory shared tables, caches, files, global memory, environment settings, and coordination records.
- Identify readers, writers, ownership, and assumptions about format, ordering, freshness, and lifecycle.
- Show how one component’s change or failure can alter another component’s behavior through that state.
- Propose explicit ownership, contracts, isolation, or synchronization where the evidence justifies it.

## Why this matters

Shared state can make a component appear independent while preserving a powerful hidden dependency. Mapping the state channel helps customers understand compatibility and partial-failure risks before changing either side.

## Evidence to use

Use schema access, permissions, cache keys, file operations, global variables, configuration reads, and tests. Verify dynamically constructed accesses when possible.

## Expected report output

A shared-state matrix with state object, readers, writers, owner, implicit assumptions, risk scenario, and recommended boundary.

## Completion and quality checks

Shared infrastructure does not necessarily mean shared logical state. Distinguish physical co-location from shared data ownership and record unresolved access paths.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
