# Data movement

**Section:** 12 · Performance and latency architecture  
**Specification ID:** `AR-12-05`  
**Customer question:** Where does transporting, copying, or transforming data dominate architectural work?

## What to include

- Trace significant data transfers across services, processes, storage, regions, or execution devices when relevant.
- Describe payload size, frequency, copies, serialization, transformations, and repeated reads.
- Identify unnecessary transfers and locality constraints, with measured or estimated costs explicitly labeled.
- Compare pushing computation to data, smaller contracts, streaming, batching, or representation changes.

## Why this matters

Customers may otherwise optimize computation while leaving the cost of moving data untouched. A data-movement view also exposes privacy, bandwidth, and memory tradeoffs of a proposed placement change.

## Evidence to use

Use payload schemas, transfer traces, serialization paths, storage access patterns, and supplied resource measurements.

## Expected report output

A data-movement map and table with source, destination, payload, volume basis, transformation, observed cost, and alternative.

## Completion and quality checks

Do not invent transfer volumes or provider charges. Account for freshness, ordering, access control, and recovery when suggesting local copies or streaming.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
