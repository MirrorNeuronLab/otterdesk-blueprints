# Prioritized hotspot map

**Section:** 06 · Architecture hotspots  
**Specification ID:** `AR-06-07`  
**Customer question:** Which components should receive architectural attention first, and why?

## What to include

- Combine complexity, churn, structural influence, production criticality, corrective work, and test gaps without hiding the individual signals.
- Explain the prioritization rule, missing data handling, and any weighting or normalization.
- Provide a small ranked set of hotspots with the concrete risk scenario and supporting evidence.
- Identify stable high-complexity areas, low-confidence candidates, and hotspots already being addressed.

## Why this matters

The combined view translates several technical analyses into a short, defensible work queue. Exposing the contributing signals lets customers challenge the ranking and adapt it to their constraints.

## Evidence to use

Use the six signal specifications in this section, matched to the same component mapping and compatible observation windows.

## Expected report output

A hotspot table or minimal map with component, signal values, impact, confidence, rationale, and linked next action.

## Completion and quality checks

Do not invent a universal health score or treat missing signals as zero risk. Show whether reasonable weighting changes alter the top priorities.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

## Related specifications

- [Hotspot growth](../architecture-evolution/hotspot_growth_spec.md)
- [Priority and ordering](../prioritized-recommendations/priority_and_ordering_spec.md)

---

[Section contents](README.md) · [Full index](../INDEX.md)
