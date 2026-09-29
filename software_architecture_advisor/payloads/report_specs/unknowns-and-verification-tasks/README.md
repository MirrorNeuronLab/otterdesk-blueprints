# 22. Unknowns and verification tasks

Make analysis limits explicit and convert consequential uncertainty into concrete, bounded information-gathering work.

This section contains **4 aspect specifications**. Each defines
what the report should contain, why the content matters, what evidence to use,
the expected output, and the completion checks.

## Aspect specifications

| ID | Aspect | Customer question |
| --- | --- | --- |
| `AR-22-01` | [Undetermined findings](undetermined_findings_spec.md) | Which important questions could not be answered from the available evidence? |
| `AR-22-02` | [Missing runtime information](missing_runtime_information_spec.md) | What operational evidence is needed to validate the static architecture model? |
| `AR-22-03` | [Assumptions register](assumptions_register_spec.md) | Which unverified premises are influencing the report’s conclusions? |
| `AR-22-04` | [Next measurements and verification tasks](next_measurements_and_verification_tasks_spec.md) | What should we check next to reduce the most consequential uncertainty? |

## Related report sections

- [10. Reliability and failure architecture](../reliability-and-failure-architecture/README.md) — Assess how architectural boundaries, state, and recovery mechanisms behave under explicitly scoped failure scenarios.
- [18. Concrete prioritized recommendations](../prioritized-recommendations/README.md) — Convert findings into a short, traceable set of actions with impact, effort, priority, and verifiable outcomes.
- [21. Evidence and confidence](../evidence-and-confidence/README.md) — Make every material claim auditable, scoped, and explicit about what is observed, inferred, assumed, or not known.

## Reporting rule

Evaluate applicability and available evidence before populating an aspect.
Do not fill a missing observation with a plausible claim. Reuse canonical finding
IDs when this section interprets evidence also used elsewhere.

[Shared report conventions](../REPORT_CONVENTIONS.md) · [Full index](../INDEX.md)
