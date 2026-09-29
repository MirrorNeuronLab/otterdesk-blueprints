# 16. Decision and what-if analysis

Evaluate concrete architectural changes as bounded scenarios, with dependencies, tradeoffs, and uncertainty made explicit.

This section contains **6 aspect specifications**. Each defines
what the report should contain, why the content matters, what evidence to use,
the expected output, and the completion checks.

## Aspect specifications

| ID | Aspect | Customer question |
| --- | --- | --- |
| `AR-16-01` | [Service split scenarios](service_split_scenarios_spec.md) | What would happen if this service were split along a proposed seam? |
| `AR-16-02` | [Safe module extraction](safe_module_extraction_spec.md) | Can this module be extracted without breaking its consumers or hidden obligations? |
| `AR-16-03` | [Technology replacement](technology_replacement_spec.md) | What would replacing a database, queue, framework, or other platform actually affect? |
| `AR-16-04` | [Workload relocation](workload_relocation_spec.md) | What changes if this work moves to another service, process, host, or environment? |
| `AR-16-05` | [Component elimination](component_elimination_spec.md) | What would break or need to move if we removed this component? |
| `AR-16-06` | [Microservice independence](microservice_independence_spec.md) | In what ways is this microservice actually independent, and in what ways is it not? |

## Related report sections

- [05. Change blast-radius analysis](../change-blast-radius-analysis/README.md) — For a specific proposed change, identify what may be affected, why, and how to validate the result.
- [17. Alternative target architectures](../alternative-target-architectures/README.md) — Offer comparable intervention options rather than a single prescriptive redesign, including the consequences of retaining the current architecture.
- [19. Sequenced migration and refactoring roadmap](../sequenced-migration-roadmap/README.md) — Turn selected recommendations into a safe sequence with explicit dependencies, compatibility windows, validation gates, and rollback constraints.

## Reporting rule

Evaluate applicability and available evidence before populating an aspect.
Do not fill a missing observation with a plausible claim. Reuse canonical finding
IDs when this section interprets evidence also used elsewhere.

[Shared report conventions](../REPORT_CONVENTIONS.md) · [Full index](../INDEX.md)
