# 10. Reliability and failure architecture

Assess how architectural boundaries, state, and recovery mechanisms behave under explicitly scoped failure scenarios.

This section contains **6 aspect specifications**. Each defines
what the report should contain, why the content matters, what evidence to use,
the expected output, and the completion checks.

## Aspect specifications

| ID | Aspect | Customer question |
| --- | --- | --- |
| `AR-10-01` | [Single points of failure](single_points_of_failure_spec.md) | Which individual failures can prevent an important capability from operating? |
| `AR-10-02` | [Failure cascades](failure_cascades_spec.md) | How can one local failure spread to otherwise healthy parts of the system? |
| `AR-10-03` | [Dependency unavailability](dependency_unavailability_spec.md) | What happens when an important dependency is slow, unreachable, or returns errors? |
| `AR-10-04` | [State inconsistency risks](state_inconsistency_risks_spec.md) | Which failures can leave the system believing mutually incompatible things? |
| `AR-10-05` | [Restart and retry behavior](restart_and_retry_behavior_spec.md) | Can interrupted work resume safely after a process or host restarts? |
| `AR-10-06` | [Recovery mechanism gaps](recovery_mechanism_gaps_spec.md) | Where does the architecture lack a workable path back to a correct operating state? |

## Related report sections

- [08. Data and state ownership](../data-and-state-ownership/README.md) — Make ownership, access, durability, consistency, and failure behavior explicit for important data and operational state.
- [09. Critical workflow analysis](../critical-workflow-analysis/README.md) — Explain important end-to-end behavior and the architectural constraints hidden within execution sequences.
- [22. Unknowns and verification tasks](../unknowns-and-verification-tasks/README.md) — Make analysis limits explicit and convert consequential uncertainty into concrete, bounded information-gathering work.

## Reporting rule

Evaluate applicability and available evidence before populating an aspect.
Do not fill a missing observation with a plausible claim. Reuse canonical finding
IDs when this section interprets evidence also used elsewhere.

[Shared report conventions](../REPORT_CONVENTIONS.md) · [Full index](../INDEX.md)
