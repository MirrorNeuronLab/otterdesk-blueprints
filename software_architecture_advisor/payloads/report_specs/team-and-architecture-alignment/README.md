# 15. Team and architecture alignment

Identify where technical boundaries and actual accountability support or obstruct coordinated delivery without evaluating individual employees.

This section contains **5 aspect specifications**. Each defines
what the report should contain, why the content matters, what evidence to use,
the expected output, and the completion checks.

## Aspect specifications

| ID | Aspect | Customer question |
| --- | --- | --- |
| `AR-15-01` | [Code ownership](code_ownership_spec.md) | Who maintains and reviews each important part of the implementation? |
| `AR-15-02` | [Team ownership](team_ownership_spec.md) | Which team is accountable for each capability, service, and operational outcome? |
| `AR-15-03` | [Team-to-service boundary alignment](team_to_service_boundary_alignment_spec.md) | Do technical units match the responsibilities teams can actually own independently? |
| `AR-15-04` | [Cross-team change patterns](cross_team_change_patterns_spec.md) | Which kinds of changes repeatedly require coordination across teams? |
| `AR-15-05` | [Shared subsystem coordination](shared_subsystem_coordination_spec.md) | Where do several teams repeatedly contend for the same architectural decision or release? |

## Related report sections

- [03. Natural boundaries versus current boundaries](../natural-boundaries-vs-current-boundaries/README.md) — Identify where responsibility, data, and change patterns suggest better boundaries while preserving explicit tradeoffs.
- [14. Architecture evolution](../architecture-evolution/README.md) — Compare meaningful architectural changes over time using compatible snapshots and clearly defined history windows.
- [20. Business impact](../business-impact/README.md) — Translate architectural mechanisms into decision-relevant outcomes, keeping measured results, estimates, and hypotheses separate.

## Reporting rule

Evaluate applicability and available evidence before populating an aspect.
Do not fill a missing observation with a plausible claim. Reuse canonical finding
IDs when this section interprets evidence also used elsewhere.

[Shared report conventions](../REPORT_CONVENTIONS.md) · [Full index](../INDEX.md)
