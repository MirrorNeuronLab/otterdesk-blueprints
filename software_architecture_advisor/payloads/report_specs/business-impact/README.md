# 20. Business impact

Translate architectural mechanisms into decision-relevant outcomes, keeping measured results, estimates, and hypotheses separate.

This section contains **8 aspect specifications**. Each defines
what the report should contain, why the content matters, what evidence to use,
the expected output, and the completion checks.

## Aspect specifications

| ID | Aspect | Customer question |
| --- | --- | --- |
| `AR-20-01` | [Change lead time](change_lead_time_spec.md) | How does the architecture influence the time needed to deliver a meaningful change? |
| `AR-20-02` | [Release risk](release_risk_spec.md) | How does the architecture affect the chance or consequence of a problematic release? |
| `AR-20-03` | [Incident likelihood](incident_likelihood_spec.md) | What does the available evidence say about architectural contributors to incident risk? |
| `AR-20-04` | [Developer coordination cost](developer_coordination_cost_spec.md) | Which architectural dependencies create avoidable coordination work? |
| `AR-20-05` | [Infrastructure cost](infrastructure_cost_spec.md) | Which architectural choices drive recurring infrastructure cost, and what could change it? |
| `AR-20-06` | [Scaling capability](scaling_capability_spec.md) | What business growth can the architecture support, and what investment would unlock more? |
| `AR-20-07` | [Hiring and onboarding complexity](hiring_and_onboarding_complexity_spec.md) | How does the architecture affect the effort required for a new contributor to become effective? |
| `AR-20-08` | [Independent deployment](independent_deployment_spec.md) | How much release autonomy do teams or services actually have? |

## Related report sections

- [01. Executive architecture brief](../executive-architecture-brief/README.md) — Give decision-makers a concise, evidence-backed orientation and a short list of decisions that deserve attention.
- [17. Alternative target architectures](../alternative-target-architectures/README.md) — Offer comparable intervention options rather than a single prescriptive redesign, including the consequences of retaining the current architecture.
- [18. Concrete prioritized recommendations](../prioritized-recommendations/README.md) — Convert findings into a short, traceable set of actions with impact, effort, priority, and verifiable outcomes.

## Reporting rule

Evaluate applicability and available evidence before populating an aspect.
Do not fill a missing observation with a plausible claim. Reuse canonical finding
IDs when this section interprets evidence also used elsewhere.

[Shared report conventions](../REPORT_CONVENTIONS.md) · [Full index](../INDEX.md)
