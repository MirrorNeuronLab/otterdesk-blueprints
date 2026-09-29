# 23. Implementation-ready work packages

Express approved or proposed improvements as bounded tasks that a human engineer or coding agent can execute and verify under explicit authority.

This section contains **8 aspect specifications**. Each defines
what the report should contain, why the content matters, what evidence to use,
the expected output, and the completion checks.

## Aspect specifications

| ID | Aspect | Customer question |
| --- | --- | --- |
| `AR-23-01` | [Task goal](task_goal_spec.md) | What single outcome should this work package deliver? |
| `AR-23-02` | [Relevant files and components](relevant_files_and_components_spec.md) | Where should the implementer look, and which adjacent areas could be affected? |
| `AR-23-03` | [Architectural constraints](architectural_constraints_spec.md) | What properties and boundaries must the implementation preserve? |
| `AR-23-04` | [Non-goals](non_goals_spec.md) | What work should explicitly not be included in this task? |
| `AR-23-05` | [Migration steps within a work package](migration_steps_spec.md) | What sequence should the implementer follow to reach the task goal safely? |
| `AR-23-06` | [Required tests](required_tests_spec.md) | What checks must accompany this work before it can be accepted? |
| `AR-23-07` | [Acceptance criteria](acceptance_criteria_spec.md) | What objective evidence allows this task to be accepted? |
| `AR-23-08` | [Coding-agent handoff](coding_agent_handoff_spec.md) | Can a coding agent execute this bounded task without guessing the intent or its authority? |

## Related report sections

- [05. Change blast-radius analysis](../change-blast-radius-analysis/README.md) — For a specific proposed change, identify what may be affected, why, and how to validate the result.
- [18. Concrete prioritized recommendations](../prioritized-recommendations/README.md) — Convert findings into a short, traceable set of actions with impact, effort, priority, and verifiable outcomes.
- [19. Sequenced migration and refactoring roadmap](../sequenced-migration-roadmap/README.md) — Turn selected recommendations into a safe sequence with explicit dependencies, compatibility windows, validation gates, and rollback constraints.

## Reporting rule

Evaluate applicability and available evidence before populating an aspect.
Do not fill a missing observation with a plausible claim. Reuse canonical finding
IDs when this section interprets evidence also used elsewhere.

[Shared report conventions](../REPORT_CONVENTIONS.md) · [Full index](../INDEX.md)
