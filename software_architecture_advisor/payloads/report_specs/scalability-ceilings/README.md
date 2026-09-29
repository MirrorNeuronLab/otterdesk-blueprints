# 11. Scalability ceilings

Identify plausible capacity limits under explicit workload assumptions and distinguish measured ceilings from unverified scaling hypotheses.

This section contains **6 aspect specifications**. Each defines
what the report should contain, why the content matters, what evidence to use,
the expected output, and the completion checks.

## Aspect specifications

| ID | Aspect | Customer question |
| --- | --- | --- |
| `AR-11-01` | [First limiting component](first_limiting_component_spec.md) | Under a defined growth scenario, which component is likely to constrain useful throughput first? |
| `AR-11-02` | [Bottleneck mechanisms](bottleneck_mechanisms_spec.md) | Why would a proposed bottleneck constrain the system? |
| `AR-11-03` | [Resource capacity constraints](resource_capacity_constraints_spec.md) | Which CPU, memory, network, storage, database, or quota limits matter to growth? |
| `AR-11-04` | [Centralized bottlenecks](centralized_bottlenecks_spec.md) | Which centralized operations can cap throughput or prevent independent scaling? |
| `AR-11-05` | [Shared resource contention](shared_resource_contention_spec.md) | Where do workloads interfere because they compete for the same resources? |
| `AR-11-06` | [Tenfold and hundredfold growth scenarios](tenfold_and_hundredfold_growth_scenarios_spec.md) | What would have to change at 10× or 100× a clearly defined workload? |

## Related report sections

- [12. Performance and latency architecture](../performance-and-latency-architecture/README.md) — Focus on structural sources of delay and resource work rather than unprioritized line-level micro-optimization.
- [16. Decision and what-if analysis](../decision-and-what-if-analysis/README.md) — Evaluate concrete architectural changes as bounded scenarios, with dependencies, tradeoffs, and uncertainty made explicit.
- [20. Business impact](../business-impact/README.md) — Translate architectural mechanisms into decision-relevant outcomes, keeping measured results, estimates, and hypotheses separate.

## Reporting rule

Evaluate applicability and available evidence before populating an aspect.
Do not fill a missing observation with a plausible claim. Reuse canonical finding
IDs when this section interprets evidence also used elsewhere.

[Shared report conventions](../REPORT_CONVENTIONS.md) · [Full index](../INDEX.md)
