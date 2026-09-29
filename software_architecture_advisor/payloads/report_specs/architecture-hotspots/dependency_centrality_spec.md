# Dependency centrality

**Section:** 06 · Architecture hotspots  
**Specification ID:** `AR-06-03`  
**Customer question:** Which components occupy influential positions in the dependency structure?

## What to include

- Define the graph, node granularity, edge direction and types, and the selected centrality measures.
- Identify highly connected or intermediary components and show representative dependency paths.
- Distinguish stable shared abstractions from components that create change or operational concentration.
- Explain how centrality contributes to hotspot prioritization alongside other signals.

## Why this matters

Structural influence helps reveal where a small change could require broad review. Its value comes from explaining the dependency mechanism, not from treating a mathematical ranking as an architectural verdict.

## Evidence to use

Use a versioned dependency graph with provenance and coverage notes. Corroborate important edges and map graph nodes to meaningful components.

## Expected report output

A centrality summary with graph definition, measures, ranked components, representative paths, and interpretation of each significant result.

## Completion and quality checks

Do not treat static centrality as request volume or failure probability. A widely used stable utility may be less urgent than a less central but volatile business component.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
