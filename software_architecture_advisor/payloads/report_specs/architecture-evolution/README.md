# 14. Architecture evolution

Compare meaningful architectural changes over time using compatible snapshots and clearly defined history windows.

This section contains **6 aspect specifications**. Each defines
what the report should contain, why the content matters, what evidence to use,
the expected output, and the completion checks.

## Aspect specifications

| ID | Aspect | Customer question |
| --- | --- | --- |
| `AR-14-01` | [Coupling trends](coupling_trends_spec.md) | Are component dependencies becoming more or less constraining over time? |
| `AR-14-02` | [Hotspot growth](hotspot_growth_spec.md) | Which architectural hotspots are emerging, worsening, or improving? |
| `AR-14-03` | [Boundary deterioration](boundary_deterioration_spec.md) | Which previously useful boundaries are losing their intended separation? |
| `AR-14-04` | [Responsibility accumulation](responsibility_accumulation_spec.md) | Which components are steadily acquiring unrelated roles? |
| `AR-14-05` | [Technical debt trends](technical_debt_trends_spec.md) | Is the architecture’s unresolved maintenance burden increasing, decreasing, or changing form? |
| `AR-14-06` | [Architecture diff between releases](architecture_diff_between_releases_spec.md) | What changed architecturally between two specific releases? |

## Related report sections

- [04. Hidden coupling](../hidden-coupling/README.md) — Expose dependencies that make apparently local changes require broader coordination or produce unexpected behavior.
- [06. Architecture hotspots](../architecture-hotspots/README.md) — Identify components where structural difficulty, active change, operational importance, and weak validation combine to warrant attention.
- [07. Architecture debt and smells](../architecture-debt-and-smells/README.md) — Turn structural symptoms into evidenced architectural findings, accounting for intentional tradeoffs and the cost of remediation.

## Reporting rule

Evaluate applicability and available evidence before populating an aspect.
Do not fill a missing observation with a plausible claim. Reuse canonical finding
IDs when this section interprets evidence also used elsewhere.

[Shared report conventions](../REPORT_CONVENTIONS.md) · [Full index](../INDEX.md)
