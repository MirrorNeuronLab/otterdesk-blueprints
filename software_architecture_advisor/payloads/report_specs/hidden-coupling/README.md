# 04. Hidden coupling

Expose dependencies that make apparently local changes require broader coordination or produce unexpected behavior.

This section contains **6 aspect specifications**. Each defines
what the report should contain, why the content matters, what evidence to use,
the expected output, and the completion checks.

## Aspect specifications

| ID | Aspect | Customer question |
| --- | --- | --- |
| `AR-04-01` | [Unexpected dependencies](unexpected_dependencies_spec.md) | Which components depend on one another in ways the architecture model does not explain? |
| `AR-04-02` | [Circular dependencies](circular_dependencies_spec.md) | Which components form dependency cycles, and how do those cycles constrain change? |
| `AR-04-03` | [Temporal and co-change coupling](temporal_and_cochange_coupling_spec.md) | Which components must be used in a particular order or repeatedly change together? |
| `AR-04-04` | [Shared-state coupling](shared_state_coupling_spec.md) | Which components influence one another through state rather than explicit interfaces? |
| `AR-04-05` | [Implicit contracts](implicit_contracts_spec.md) | What unstated expectations must remain true for components to cooperate? |
| `AR-04-06` | [Cross-layer dependencies](cross_layer_dependencies_spec.md) | Where does code cross or reverse an intended architectural layer boundary? |

## Related report sections

- [05. Change blast-radius analysis](../change-blast-radius-analysis/README.md) — For a specific proposed change, identify what may be affected, why, and how to validate the result.
- [07. Architecture debt and smells](../architecture-debt-and-smells/README.md) — Turn structural symptoms into evidenced architectural findings, accounting for intentional tradeoffs and the cost of remediation.
- [14. Architecture evolution](../architecture-evolution/README.md) — Compare meaningful architectural changes over time using compatible snapshots and clearly defined history windows.

## Reporting rule

Evaluate applicability and available evidence before populating an aspect.
Do not fill a missing observation with a plausible claim. Reuse canonical finding
IDs when this section interprets evidence also used elsewhere.

[Shared report conventions](../REPORT_CONVENTIONS.md) · [Full index](../INDEX.md)
