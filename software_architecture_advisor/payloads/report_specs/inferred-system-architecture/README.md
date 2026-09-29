# 02. Inferred system architecture

Reconstruct how the implementation actually works instead of mirroring the directory tree or repeating potentially stale diagrams.

This section contains **6 aspect specifications**. Each defines
what the report should contain, why the content matters, what evidence to use,
the expected output, and the completion checks.

## Aspect specifications

| ID | Aspect | Customer question |
| --- | --- | --- |
| `AR-02-01` | [Major subsystems and responsibilities](major_subsystems_and_responsibilities_spec.md) | What are the main functional parts, and what work is each responsible for? |
| `AR-02-02` | [Service and module boundaries](service_and_module_boundaries_spec.md) | Where are the actual separation points, and how strong are those boundaries? |
| `AR-02-03` | [Runtime and deployment topology](runtime_and_deployment_topology_spec.md) | What runs where, and how do deployment and operational boundaries differ from source structure? |
| `AR-02-04` | [External dependencies](external_dependencies_spec.md) | Which third-party or out-of-scope systems does this architecture rely on? |
| `AR-02-05` | [Critical request and data flows](critical_request_and_data_flows_spec.md) | How do important requests and data travel across the system? |
| `AR-02-06` | [How the system actually works](how_the_system_actually_works_spec.md) | What operational story explains the implementation beyond its file layout? |

## Related report sections

- [08. Data and state ownership](../data-and-state-ownership/README.md) — Make ownership, access, durability, consistency, and failure behavior explicit for important data and operational state.
- [09. Critical workflow analysis](../critical-workflow-analysis/README.md) — Explain important end-to-end behavior and the architectural constraints hidden within execution sequences.
- [21. Evidence and confidence](../evidence-and-confidence/README.md) — Make every material claim auditable, scoped, and explicit about what is observed, inferred, assumed, or not known.

## Reporting rule

Evaluate applicability and available evidence before populating an aspect.
Do not fill a missing observation with a plausible claim. Reuse canonical finding
IDs when this section interprets evidence also used elsewhere.

[Shared report conventions](../REPORT_CONVENTIONS.md) · [Full index](../INDEX.md)
