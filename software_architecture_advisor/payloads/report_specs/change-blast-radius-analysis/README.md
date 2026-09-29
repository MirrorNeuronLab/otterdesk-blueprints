# 05. Change blast-radius analysis

For a specific proposed change, identify what may be affected, why, and how to validate the result.

This section contains **8 aspect specifications**. Each defines
what the report should contain, why the content matters, what evidence to use,
the expected output, and the completion checks.

## Aspect specifications

| ID | Aspect | Customer question |
| --- | --- | --- |
| `AR-05-01` | [Change scenario definition](change_scenario_definition_spec.md) | Exactly what change are we evaluating, and what counts as an impact? |
| `AR-05-02` | [Direct dependents](direct_dependents_spec.md) | Which immediate consumers need review for this change? |
| `AR-05-03` | [Transitive dependents](transitive_dependents_spec.md) | How could this change propagate beyond immediate consumers? |
| `AR-05-04` | [Affected APIs and contracts](affected_apis_and_contracts_spec.md) | Which public or internal contracts could change for consumers? |
| `AR-05-05` | [Data and schema dependencies](data_and_schema_dependencies_spec.md) | Which data consumers, migrations, and invariants are affected? |
| `AR-05-06` | [Tests to run](tests_to_run_spec.md) | Which tests provide useful evidence that this change is safe? |
| `AR-05-07` | [Affected services and deployments](affected_services_and_deployments_spec.md) | Which operational units must change, restart, or coordinate a release? |
| `AR-05-08` | [Historical co-change evidence](historical_cochange_evidence_spec.md) | What past changes suggest additional review targets for this change? |

## Related report sections

- [02. Inferred system architecture](../inferred-system-architecture/README.md) — Reconstruct how the implementation actually works instead of mirroring the directory tree or repeating potentially stale diagrams.
- [08. Data and state ownership](../data-and-state-ownership/README.md) — Make ownership, access, durability, consistency, and failure behavior explicit for important data and operational state.
- [23. Implementation-ready work packages](../implementation-ready-work-packages/README.md) — Express approved or proposed improvements as bounded tasks that a human engineer or coding agent can execute and verify under explicit authority.

## Reporting rule

Evaluate applicability and available evidence before populating an aspect.
Do not fill a missing observation with a plausible claim. Reuse canonical finding
IDs when this section interprets evidence also used elsewhere.

[Shared report conventions](../REPORT_CONVENTIONS.md) · [Full index](../INDEX.md)
