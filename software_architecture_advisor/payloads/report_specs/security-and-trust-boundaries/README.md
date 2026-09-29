# 13. Security and trust boundaries

Describe architectural security exposure and control boundaries without implying that an architecture review is a complete security audit.

This section contains **6 aspect specifications**. Each defines
what the report should contain, why the content matters, what evidence to use,
the expected output, and the completion checks.

## Aspect specifications

| ID | Aspect | Customer question |
| --- | --- | --- |
| `AR-13-01` | [Trust boundary map](trust_boundary_map_spec.md) | Where does the system accept data or actions from an actor with a different trust level? |
| `AR-13-02` | [Privilege concentration](privilege_concentration_spec.md) | Which identities or components hold authority far broader than their normal responsibilities? |
| `AR-13-03` | [Sensitive-data flows](sensitive_data_flows_spec.md) | Where does sensitive information enter, move, persist, and leave the architecture? |
| `AR-13-04` | [Authentication and authorization boundaries](authentication_and_authorization_boundaries_spec.md) | Where are identity and permission decisions made and enforced? |
| `AR-13-05` | [Dependency and security exposure](dependency_and_security_exposure_spec.md) | Which dependencies or architectural interfaces expand the security exposure under review? |
| `AR-13-06` | [Security blast radius](security_blast_radius_spec.md) | What could an attacker or unauthorized actor reach from a compromised architectural unit? |

## Related report sections

- [02. Inferred system architecture](../inferred-system-architecture/README.md) — Reconstruct how the implementation actually works instead of mirroring the directory tree or repeating potentially stale diagrams.
- [08. Data and state ownership](../data-and-state-ownership/README.md) — Make ownership, access, durability, consistency, and failure behavior explicit for important data and operational state.
- [21. Evidence and confidence](../evidence-and-confidence/README.md) — Make every material claim auditable, scoped, and explicit about what is observed, inferred, assumed, or not known.

## Reporting rule

Evaluate applicability and available evidence before populating an aspect.
Do not fill a missing observation with a plausible claim. Reuse canonical finding
IDs when this section interprets evidence also used elsewhere.

[Shared report conventions](../REPORT_CONVENTIONS.md) · [Full index](../INDEX.md)
