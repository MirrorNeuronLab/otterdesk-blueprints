# 07. Architecture debt and smells

Turn structural symptoms into evidenced architectural findings, accounting for intentional tradeoffs and the cost of remediation.

This section contains **9 aspect specifications**. Each defines
what the report should contain, why the content matters, what evidence to use,
the expected output, and the completion checks.

## Aspect specifications

| ID | Aspect | Customer question |
| --- | --- | --- |
| `AR-07-01` | [God components](god_components_spec.md) | Which components accumulate excessive responsibilities or authority? |
| `AR-07-02` | [Dependency cycles as architectural debt](dependency_cycles_spec.md) | Which dependency cycles create enough ongoing cost to justify intervention? |
| `AR-07-03` | [Layer violations as architectural debt](layer_violations_spec.md) | Which layer-rule exceptions create a meaningful maintenance obligation? |
| `AR-07-04` | [Excessive centralization](excessive_centralization_spec.md) | Where does centralized control or state impose an avoidable system-wide constraint? |
| `AR-07-05` | [Leaky abstractions](leaky_abstractions_spec.md) | Where must consumers understand details that an interface is meant to hide? |
| `AR-07-06` | [Duplicate mechanisms](duplicate_mechanisms_spec.md) | Where do multiple implementations solve the same architectural problem inconsistently? |
| `AR-07-07` | [Ownership boundary mismatches](ownership_boundary_mismatches_spec.md) | Where are architectural responsibilities assigned in ways that create unresolved control or coordination? |
| `AR-07-08` | [Fan-in and fan-out](fan_in_and_fan_out_spec.md) | Where do unusually broad dependency relationships create a practical design concern? |
| `AR-07-09` | [Architecture drift](architecture_drift_spec.md) | Where has implementation moved away from an agreed or previously observed architecture? |

## Related report sections

- [03. Natural boundaries versus current boundaries](../natural-boundaries-vs-current-boundaries/README.md) — Identify where responsibility, data, and change patterns suggest better boundaries while preserving explicit tradeoffs.
- [04. Hidden coupling](../hidden-coupling/README.md) — Expose dependencies that make apparently local changes require broader coordination or produce unexpected behavior.
- [18. Concrete prioritized recommendations](../prioritized-recommendations/README.md) — Convert findings into a short, traceable set of actions with impact, effort, priority, and verifiable outcomes.

## Reporting rule

Evaluate applicability and available evidence before populating an aspect.
Do not fill a missing observation with a plausible claim. Reuse canonical finding
IDs when this section interprets evidence also used elsewhere.

[Shared report conventions](../REPORT_CONVENTIONS.md) · [Full index](../INDEX.md)
