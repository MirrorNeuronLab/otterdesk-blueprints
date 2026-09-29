# 12. Performance and latency architecture

Focus on structural sources of delay and resource work rather than unprioritized line-level micro-optimization.

This section contains **6 aspect specifications**. Each defines
what the report should contain, why the content matters, what evidence to use,
the expected output, and the completion checks.

## Aspect specifications

| ID | Aspect | Customer question |
| --- | --- | --- |
| `AR-12-01` | [Critical latency paths](critical_latency_paths_spec.md) | Which architectural stages account for delay in important user or job outcomes? |
| `AR-12-02` | [Serial dependencies](serial_dependencies_spec.md) | Which sequential steps are necessary, and which could be overlapped or removed? |
| `AR-12-03` | [Excessive remote calls](excessive_remote_calls_spec.md) | Where does the architecture perform avoidable network interactions? |
| `AR-12-04` | [Chatty service boundaries](chatty_service_boundaries_spec.md) | Do service contracts force repeated back-and-forth to complete one coherent task? |
| `AR-12-05` | [Data movement](data_movement_spec.md) | Where does transporting, copying, or transforming data dominate architectural work? |
| `AR-12-06` | [Synchronization points](synchronization_points_spec.md) | Where do locks, barriers, transactions, or coordination waits delay independent work? |

## Related report sections

- [09. Critical workflow analysis](../critical-workflow-analysis/README.md) — Explain important end-to-end behavior and the architectural constraints hidden within execution sequences.
- [11. Scalability ceilings](../scalability-ceilings/README.md) — Identify plausible capacity limits under explicit workload assumptions and distinguish measured ceilings from unverified scaling hypotheses.
- [20. Business impact](../business-impact/README.md) — Translate architectural mechanisms into decision-relevant outcomes, keeping measured results, estimates, and hypotheses separate.

## Reporting rule

Evaluate applicability and available evidence before populating an aspect.
Do not fill a missing observation with a plausible claim. Reuse canonical finding
IDs when this section interprets evidence also used elsewhere.

[Shared report conventions](../REPORT_CONVENTIONS.md) · [Full index](../INDEX.md)
