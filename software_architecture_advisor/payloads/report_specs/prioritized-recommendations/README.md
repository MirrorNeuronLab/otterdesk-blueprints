# 18. Concrete prioritized recommendations

Convert findings into a short, traceable set of actions with impact, effort, priority, and verifiable outcomes.

This section contains **7 aspect specifications**. Each defines
what the report should contain, why the content matters, what evidence to use,
the expected output, and the completion checks.

## Aspect specifications

| ID | Aspect | Customer question |
| --- | --- | --- |
| `AR-18-01` | [Finding statement](finding_statement_spec.md) | What exactly is wrong or worth improving, and under what conditions? |
| `AR-18-02` | [Supporting evidence for a recommendation](supporting_evidence_spec.md) | What evidence supports this finding and the proposed response? |
| `AR-18-03` | [Impact assessment](impact_assessment_spec.md) | Why does this finding matter to the customer? |
| `AR-18-04` | [Recommended action](recommended_action_spec.md) | What specific change or investigation should the customer undertake? |
| `AR-18-05` | [Effort estimate](effort_estimate_spec.md) | What work and uncertainty determine the likely implementation effort? |
| `AR-18-06` | [Validation plan](validation_plan_spec.md) | How will we know the recommendation produced the intended improvement? |
| `AR-18-07` | [Priority and ordering](priority_and_ordering_spec.md) | Which recommendations should be undertaken first, and what must precede them? |

## Related report sections

- [01. Executive architecture brief](../executive-architecture-brief/README.md) — Give decision-makers a concise, evidence-backed orientation and a short list of decisions that deserve attention.
- [19. Sequenced migration and refactoring roadmap](../sequenced-migration-roadmap/README.md) — Turn selected recommendations into a safe sequence with explicit dependencies, compatibility windows, validation gates, and rollback constraints.
- [23. Implementation-ready work packages](../implementation-ready-work-packages/README.md) — Express approved or proposed improvements as bounded tasks that a human engineer or coding agent can execute and verify under explicit authority.

## Reporting rule

Evaluate applicability and available evidence before populating an aspect.
Do not fill a missing observation with a plausible claim. Reuse canonical finding
IDs when this section interprets evidence also used elsewhere.

[Shared report conventions](../REPORT_CONVENTIONS.md) · [Full index](../INDEX.md)
