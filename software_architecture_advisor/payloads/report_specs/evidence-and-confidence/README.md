# 21. Evidence and confidence

Make every material claim auditable, scoped, and explicit about what is observed, inferred, assumed, or not known.

This section contains **8 aspect specifications**. Each defines
what the report should contain, why the content matters, what evidence to use,
the expected output, and the completion checks.

## Aspect specifications

| ID | Aspect | Customer question |
| --- | --- | --- |
| `AR-21-01` | [Source-code evidence](source_code_evidence_spec.md) | Can a reviewer locate the implementation that supports this claim? |
| `AR-21-02` | [Runtime trace evidence](runtime_trace_evidence_spec.md) | What observed execution supports the architectural behavior or timing claim? |
| `AR-21-03` | [Dependency-edge evidence](dependency_edge_evidence_spec.md) | What does each important edge mean, and where did it come from? |
| `AR-21-04` | [Historical commit evidence](historical_commit_evidence_spec.md) | Which actual changes support the report’s evolutionary claims? |
| `AR-21-05` | [Incident and test evidence](incident_and_test_evidence_spec.md) | Which failures or checks demonstrate the claimed behavior? |
| `AR-21-06` | [Confidence assessment](confidence_assessment_spec.md) | How strongly does the available evidence support each material claim? |
| `AR-21-07` | [Counterevidence and uncertainty](counterevidence_and_uncertainty_spec.md) | What could make this finding or recommendation wrong? |
| `AR-21-08` | [Claim-to-evidence traceability](claim_to_evidence_traceability_spec.md) | Can every conclusion, recommendation, and work package be traced back to verifiable observations? |

## Related report sections

- [18. Concrete prioritized recommendations](../prioritized-recommendations/README.md) — Convert findings into a short, traceable set of actions with impact, effort, priority, and verifiable outcomes.
- [22. Unknowns and verification tasks](../unknowns-and-verification-tasks/README.md) — Make analysis limits explicit and convert consequential uncertainty into concrete, bounded information-gathering work.
- [23. Implementation-ready work packages](../implementation-ready-work-packages/README.md) — Express approved or proposed improvements as bounded tasks that a human engineer or coding agent can execute and verify under explicit authority.

## Reporting rule

Evaluate applicability and available evidence before populating an aspect.
Do not fill a missing observation with a plausible claim. Reuse canonical finding
IDs when this section interprets evidence also used elsewhere.

[Shared report conventions](../REPORT_CONVENTIONS.md) · [Full index](../INDEX.md)
