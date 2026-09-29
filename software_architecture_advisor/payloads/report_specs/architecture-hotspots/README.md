# 06. Architecture hotspots

Identify components where structural difficulty, active change, operational importance, and weak validation combine to warrant attention.

This section contains **7 aspect specifications**. Each defines
what the report should contain, why the content matters, what evidence to use,
the expected output, and the completion checks.

## Aspect specifications

| ID | Aspect | Customer question |
| --- | --- | --- |
| `AR-06-01` | [Code complexity](code_complexity_spec.md) | Where is implementation complexity concentrated at an architectural level? |
| `AR-06-02` | [Git churn](git_churn_spec.md) | Which architectural areas absorb the most change? |
| `AR-06-03` | [Dependency centrality](dependency_centrality_spec.md) | Which components occupy influential positions in the dependency structure? |
| `AR-06-04` | [Production criticality](production_criticality_spec.md) | Which components support the outcomes the customer can least afford to lose? |
| `AR-06-05` | [Bug-fix concentration](bug_fix_concentration_spec.md) | Where does corrective work repeatedly accumulate? |
| `AR-06-06` | [Test coverage gaps](test_coverage_gaps_spec.md) | Where do important architectural behaviors lack credible verification? |
| `AR-06-07` | [Prioritized hotspot map](prioritized_hotspot_map_spec.md) | Which components should receive architectural attention first, and why? |

## Related report sections

- [07. Architecture debt and smells](../architecture-debt-and-smells/README.md) — Turn structural symptoms into evidenced architectural findings, accounting for intentional tradeoffs and the cost of remediation.
- [14. Architecture evolution](../architecture-evolution/README.md) — Compare meaningful architectural changes over time using compatible snapshots and clearly defined history windows.
- [18. Concrete prioritized recommendations](../prioritized-recommendations/README.md) — Convert findings into a short, traceable set of actions with impact, effort, priority, and verifiable outcomes.

## Reporting rule

Evaluate applicability and available evidence before populating an aspect.
Do not fill a missing observation with a plausible claim. Reuse canonical finding
IDs when this section interprets evidence also used elsewhere.

[Shared report conventions](../REPORT_CONVENTIONS.md) · [Full index](../INDEX.md)
