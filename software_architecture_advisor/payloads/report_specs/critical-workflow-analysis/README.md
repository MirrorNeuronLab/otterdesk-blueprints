# 09. Critical workflow analysis

Explain important end-to-end behavior and the architectural constraints hidden within execution sequences.

This section contains **7 aspect specifications**. Each defines
what the report should contain, why the content matters, what evidence to use,
the expected output, and the completion checks.

## Aspect specifications

| ID | Aspect | Customer question |
| --- | --- | --- |
| `AR-09-01` | [End-to-end workflow](end_to_end_workflow_spec.md) | How does an important customer or operational task complete? |
| `AR-09-02` | [Critical workflow path](critical_path_spec.md) | Which dependent steps determine when this workflow can complete? |
| `AR-09-03` | [Workflow failure points](failure_points_spec.md) | Where can this workflow fail, and what does the customer observe? |
| `AR-09-04` | [Cross-boundary calls](cross_boundary_calls_spec.md) | Which workflow steps cross a boundary that adds coordination or operational obligations? |
| `AR-09-05` | [Workflow state transitions](state_transitions_spec.md) | What states can the work occupy, and which transitions are valid? |
| `AR-09-06` | [Retry and idempotency behavior](retry_and_idempotency_behavior_spec.md) | Can this workflow be retried without losing work or duplicating effects? |
| `AR-09-07` | [Hidden workflow dependencies](hidden_workflow_dependencies_spec.md) | What must be true outside the explicit workflow graph for it to succeed? |

## Related report sections

- [08. Data and state ownership](../data-and-state-ownership/README.md) — Make ownership, access, durability, consistency, and failure behavior explicit for important data and operational state.
- [10. Reliability and failure architecture](../reliability-and-failure-architecture/README.md) — Assess how architectural boundaries, state, and recovery mechanisms behave under explicitly scoped failure scenarios.
- [12. Performance and latency architecture](../performance-and-latency-architecture/README.md) — Focus on structural sources of delay and resource work rather than unprioritized line-level micro-optimization.

## Reporting rule

Evaluate applicability and available evidence before populating an aspect.
Do not fill a missing observation with a plausible claim. Reuse canonical finding
IDs when this section interprets evidence also used elsewhere.

[Shared report conventions](../REPORT_CONVENTIONS.md) · [Full index](../INDEX.md)
