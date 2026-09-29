# 01. Executive architecture brief

Give decision-makers a concise, evidence-backed orientation and a short list of decisions that deserve attention.

This section contains **5 aspect specifications**. Each defines
what the report should contain, why the content matters, what evidence to use,
the expected output, and the completion checks.

## Aspect specifications

| ID | Aspect | Customer question |
| --- | --- | --- |
| `AR-01-01` | [What the system does](what_the_system_does_spec.md) | What business work does this system perform, for whom, and where does its responsibility end? |
| `AR-01-02` | [Overall architecture shape](overall_architecture_shape_spec.md) | How is the system organized, and which architectural choices define how it operates? |
| `AR-01-03` | [Major strengths and weaknesses](major_strengths_and_weaknesses_spec.md) | What should we preserve, and what currently obstructs our goals? |
| `AR-01-04` | [Top architectural risks](top_architectural_risks_spec.md) | Which three to five architectural risks most deserve management attention? |
| `AR-01-05` | [Immediate versus later priorities](immediate_vs_later_priorities_spec.md) | What should we address now, plan next, and deliberately leave alone? |

## Related report sections

- [02. Inferred system architecture](../inferred-system-architecture/README.md) — Reconstruct how the implementation actually works instead of mirroring the directory tree or repeating potentially stale diagrams.
- [18. Concrete prioritized recommendations](../prioritized-recommendations/README.md) — Convert findings into a short, traceable set of actions with impact, effort, priority, and verifiable outcomes.
- [20. Business impact](../business-impact/README.md) — Translate architectural mechanisms into decision-relevant outcomes, keeping measured results, estimates, and hypotheses separate.

## Reporting rule

Evaluate applicability and available evidence before populating an aspect.
Do not fill a missing observation with a plausible claim. Reuse canonical finding
IDs when this section interprets evidence also used elsewhere.

[Shared report conventions](../REPORT_CONVENTIONS.md) · [Full index](../INDEX.md)
