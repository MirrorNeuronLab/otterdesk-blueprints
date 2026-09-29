# 03. Natural boundaries versus current boundaries

Identify where responsibility, data, and change patterns suggest better boundaries while preserving explicit tradeoffs.

This section contains **5 aspect specifications**. Each defines
what the report should contain, why the content matters, what evidence to use,
the expected output, and the completion checks.

## Aspect specifications

| ID | Aspect | Customer question |
| --- | --- | --- |
| `AR-03-01` | [Recommended component boundaries](recommended_component_boundaries_spec.md) | Where would boundaries better match responsibilities and independent change? |
| `AR-03-02` | [Mixed responsibilities](mixed_responsibilities_spec.md) | Which components combine concerns that should change or be governed separately? |
| `AR-03-03` | [Merge candidates](merge_candidates_spec.md) | Which separated components create overhead without meaningful independence? |
| `AR-03-04` | [Extraction and decomposition candidates](extraction_and_decomposition_candidates_spec.md) | What can be separated safely, and what prevents separation today? |
| `AR-03-05` | [Domain boundary violations](domain_boundary_violations_spec.md) | Where does one domain reach into another domain’s rules or internal representation? |

## Related report sections

- [04. Hidden coupling](../hidden-coupling/README.md) — Expose dependencies that make apparently local changes require broader coordination or produce unexpected behavior.
- [15. Team and architecture alignment](../team-and-architecture-alignment/README.md) — Identify where technical boundaries and actual accountability support or obstruct coordinated delivery without evaluating individual employees.
- [17. Alternative target architectures](../alternative-target-architectures/README.md) — Offer comparable intervention options rather than a single prescriptive redesign, including the consequences of retaining the current architecture.

## Reporting rule

Evaluate applicability and available evidence before populating an aspect.
Do not fill a missing observation with a plausible claim. Reuse canonical finding
IDs when this section interprets evidence also used elsewhere.

[Shared report conventions](../REPORT_CONVENTIONS.md) · [Full index](../INDEX.md)
