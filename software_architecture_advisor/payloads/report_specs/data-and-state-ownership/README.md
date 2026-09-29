# 08. Data and state ownership

Make ownership, access, durability, consistency, and failure behavior explicit for important data and operational state.

This section contains **9 aspect specifications**. Each defines
what the report should contain, why the content matters, what evidence to use,
the expected output, and the completion checks.

## Aspect specifications

| ID | Aspect | Customer question |
| --- | --- | --- |
| `AR-08-01` | [Data ownership](data_ownership_spec.md) | Who has authority over each important data entity and its rules? |
| `AR-08-02` | [Data writers](data_writers_spec.md) | Which actors can create, update, or delete important state? |
| `AR-08-03` | [Data readers](data_readers_spec.md) | Who depends on the meaning, shape, and freshness of this data? |
| `AR-08-04` | [Sources of truth](sources_of_truth_spec.md) | Which representation is authoritative when copies disagree? |
| `AR-08-05` | [Cache topology and invalidation](cache_topology_and_invalidation_spec.md) | Where is data cached, and what keeps cached behavior acceptably correct? |
| `AR-08-06` | [Durable versus ephemeral state](durable_vs_ephemeral_state_spec.md) | What survives process loss, and what must be reconstructed? |
| `AR-08-07` | [Consistency and disagreement](consistency_and_disagreement_spec.md) | Can components hold conflicting views, and how is disagreement resolved? |
| `AR-08-08` | [Partial-failure behavior of state](partial_failure_behavior_spec.md) | What happens when only part of a multi-step state change succeeds? |
| `AR-08-09` | [CRUD and ownership matrix](crud_and_ownership_matrix_spec.md) | Can we see data authority and access patterns in one actionable view? |

## Related report sections

- [09. Critical workflow analysis](../critical-workflow-analysis/README.md) — Explain important end-to-end behavior and the architectural constraints hidden within execution sequences.
- [10. Reliability and failure architecture](../reliability-and-failure-architecture/README.md) — Assess how architectural boundaries, state, and recovery mechanisms behave under explicitly scoped failure scenarios.
- [19. Sequenced migration and refactoring roadmap](../sequenced-migration-roadmap/README.md) — Turn selected recommendations into a safe sequence with explicit dependencies, compatibility windows, validation gates, and rollback constraints.

## Reporting rule

Evaluate applicability and available evidence before populating an aspect.
Do not fill a missing observation with a plausible claim. Reuse canonical finding
IDs when this section interprets evidence also used elsewhere.

[Shared report conventions](../REPORT_CONVENTIONS.md) · [Full index](../INDEX.md)
