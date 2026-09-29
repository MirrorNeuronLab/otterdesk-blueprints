# Complete specification index

**23 report sections · 150 content specifications**

The section order follows the 23-section outline from the conversation. Folder
names use kebab-case; aspect filenames use snake_case ending in `_spec.md`.
Each aspect is a separate Markdown file. Start with the [README](README.md) and
apply the [shared report conventions](REPORT_CONVENTIONS.md).

## Section overview

| Section | Folder | Specs |
| --- | --- | ---: |
| 01. Executive architecture brief | [executive-architecture-brief/](executive-architecture-brief/README.md) | 5 |
| 02. Inferred system architecture | [inferred-system-architecture/](inferred-system-architecture/README.md) | 6 |
| 03. Natural boundaries versus current boundaries | [natural-boundaries-vs-current-boundaries/](natural-boundaries-vs-current-boundaries/README.md) | 5 |
| 04. Hidden coupling | [hidden-coupling/](hidden-coupling/README.md) | 6 |
| 05. Change blast-radius analysis | [change-blast-radius-analysis/](change-blast-radius-analysis/README.md) | 8 |
| 06. Architecture hotspots | [architecture-hotspots/](architecture-hotspots/README.md) | 7 |
| 07. Architecture debt and smells | [architecture-debt-and-smells/](architecture-debt-and-smells/README.md) | 9 |
| 08. Data and state ownership | [data-and-state-ownership/](data-and-state-ownership/README.md) | 9 |
| 09. Critical workflow analysis | [critical-workflow-analysis/](critical-workflow-analysis/README.md) | 7 |
| 10. Reliability and failure architecture | [reliability-and-failure-architecture/](reliability-and-failure-architecture/README.md) | 6 |
| 11. Scalability ceilings | [scalability-ceilings/](scalability-ceilings/README.md) | 6 |
| 12. Performance and latency architecture | [performance-and-latency-architecture/](performance-and-latency-architecture/README.md) | 6 |
| 13. Security and trust boundaries | [security-and-trust-boundaries/](security-and-trust-boundaries/README.md) | 6 |
| 14. Architecture evolution | [architecture-evolution/](architecture-evolution/README.md) | 6 |
| 15. Team and architecture alignment | [team-and-architecture-alignment/](team-and-architecture-alignment/README.md) | 5 |
| 16. Decision and what-if analysis | [decision-and-what-if-analysis/](decision-and-what-if-analysis/README.md) | 6 |
| 17. Alternative target architectures | [alternative-target-architectures/](alternative-target-architectures/README.md) | 4 |
| 18. Concrete prioritized recommendations | [prioritized-recommendations/](prioritized-recommendations/README.md) | 7 |
| 19. Sequenced migration and refactoring roadmap | [sequenced-migration-roadmap/](sequenced-migration-roadmap/README.md) | 8 |
| 20. Business impact | [business-impact/](business-impact/README.md) | 8 |
| 21. Evidence and confidence | [evidence-and-confidence/](evidence-and-confidence/README.md) | 8 |
| 22. Unknowns and verification tasks | [unknowns-and-verification-tasks/](unknowns-and-verification-tasks/README.md) | 4 |
| 23. Implementation-ready work packages | [implementation-ready-work-packages/](implementation-ready-work-packages/README.md) | 8 |

## All aspect files

### 01. Executive architecture brief

Give decision-makers a concise, evidence-backed orientation and a short list of decisions that deserve attention.

- `AR-01-01` — [what_the_system_does_spec.md](executive-architecture-brief/what_the_system_does_spec.md) — What the system does.
- `AR-01-02` — [overall_architecture_shape_spec.md](executive-architecture-brief/overall_architecture_shape_spec.md) — Overall architecture shape.
- `AR-01-03` — [major_strengths_and_weaknesses_spec.md](executive-architecture-brief/major_strengths_and_weaknesses_spec.md) — Major strengths and weaknesses.
- `AR-01-04` — [top_architectural_risks_spec.md](executive-architecture-brief/top_architectural_risks_spec.md) — Top architectural risks.
- `AR-01-05` — [immediate_vs_later_priorities_spec.md](executive-architecture-brief/immediate_vs_later_priorities_spec.md) — Immediate versus later priorities.

### 02. Inferred system architecture

Reconstruct how the implementation actually works instead of mirroring the directory tree or repeating potentially stale diagrams.

- `AR-02-01` — [major_subsystems_and_responsibilities_spec.md](inferred-system-architecture/major_subsystems_and_responsibilities_spec.md) — Major subsystems and responsibilities.
- `AR-02-02` — [service_and_module_boundaries_spec.md](inferred-system-architecture/service_and_module_boundaries_spec.md) — Service and module boundaries.
- `AR-02-03` — [runtime_and_deployment_topology_spec.md](inferred-system-architecture/runtime_and_deployment_topology_spec.md) — Runtime and deployment topology.
- `AR-02-04` — [external_dependencies_spec.md](inferred-system-architecture/external_dependencies_spec.md) — External dependencies.
- `AR-02-05` — [critical_request_and_data_flows_spec.md](inferred-system-architecture/critical_request_and_data_flows_spec.md) — Critical request and data flows.
- `AR-02-06` — [how_the_system_actually_works_spec.md](inferred-system-architecture/how_the_system_actually_works_spec.md) — How the system actually works.

### 03. Natural boundaries versus current boundaries

Identify where responsibility, data, and change patterns suggest better boundaries while preserving explicit tradeoffs.

- `AR-03-01` — [recommended_component_boundaries_spec.md](natural-boundaries-vs-current-boundaries/recommended_component_boundaries_spec.md) — Recommended component boundaries.
- `AR-03-02` — [mixed_responsibilities_spec.md](natural-boundaries-vs-current-boundaries/mixed_responsibilities_spec.md) — Mixed responsibilities.
- `AR-03-03` — [merge_candidates_spec.md](natural-boundaries-vs-current-boundaries/merge_candidates_spec.md) — Merge candidates.
- `AR-03-04` — [extraction_and_decomposition_candidates_spec.md](natural-boundaries-vs-current-boundaries/extraction_and_decomposition_candidates_spec.md) — Extraction and decomposition candidates.
- `AR-03-05` — [domain_boundary_violations_spec.md](natural-boundaries-vs-current-boundaries/domain_boundary_violations_spec.md) — Domain boundary violations.

### 04. Hidden coupling

Expose dependencies that make apparently local changes require broader coordination or produce unexpected behavior.

- `AR-04-01` — [unexpected_dependencies_spec.md](hidden-coupling/unexpected_dependencies_spec.md) — Unexpected dependencies.
- `AR-04-02` — [circular_dependencies_spec.md](hidden-coupling/circular_dependencies_spec.md) — Circular dependencies.
- `AR-04-03` — [temporal_and_cochange_coupling_spec.md](hidden-coupling/temporal_and_cochange_coupling_spec.md) — Temporal and co-change coupling.
- `AR-04-04` — [shared_state_coupling_spec.md](hidden-coupling/shared_state_coupling_spec.md) — Shared-state coupling.
- `AR-04-05` — [implicit_contracts_spec.md](hidden-coupling/implicit_contracts_spec.md) — Implicit contracts.
- `AR-04-06` — [cross_layer_dependencies_spec.md](hidden-coupling/cross_layer_dependencies_spec.md) — Cross-layer dependencies.

### 05. Change blast-radius analysis

For a specific proposed change, identify what may be affected, why, and how to validate the result.

- `AR-05-01` — [change_scenario_definition_spec.md](change-blast-radius-analysis/change_scenario_definition_spec.md) — Change scenario definition.
- `AR-05-02` — [direct_dependents_spec.md](change-blast-radius-analysis/direct_dependents_spec.md) — Direct dependents.
- `AR-05-03` — [transitive_dependents_spec.md](change-blast-radius-analysis/transitive_dependents_spec.md) — Transitive dependents.
- `AR-05-04` — [affected_apis_and_contracts_spec.md](change-blast-radius-analysis/affected_apis_and_contracts_spec.md) — Affected APIs and contracts.
- `AR-05-05` — [data_and_schema_dependencies_spec.md](change-blast-radius-analysis/data_and_schema_dependencies_spec.md) — Data and schema dependencies.
- `AR-05-06` — [tests_to_run_spec.md](change-blast-radius-analysis/tests_to_run_spec.md) — Tests to run.
- `AR-05-07` — [affected_services_and_deployments_spec.md](change-blast-radius-analysis/affected_services_and_deployments_spec.md) — Affected services and deployments.
- `AR-05-08` — [historical_cochange_evidence_spec.md](change-blast-radius-analysis/historical_cochange_evidence_spec.md) — Historical co-change evidence.

### 06. Architecture hotspots

Identify components where structural difficulty, active change, operational importance, and weak validation combine to warrant attention.

- `AR-06-01` — [code_complexity_spec.md](architecture-hotspots/code_complexity_spec.md) — Code complexity.
- `AR-06-02` — [git_churn_spec.md](architecture-hotspots/git_churn_spec.md) — Git churn.
- `AR-06-03` — [dependency_centrality_spec.md](architecture-hotspots/dependency_centrality_spec.md) — Dependency centrality.
- `AR-06-04` — [production_criticality_spec.md](architecture-hotspots/production_criticality_spec.md) — Production criticality.
- `AR-06-05` — [bug_fix_concentration_spec.md](architecture-hotspots/bug_fix_concentration_spec.md) — Bug-fix concentration.
- `AR-06-06` — [test_coverage_gaps_spec.md](architecture-hotspots/test_coverage_gaps_spec.md) — Test coverage gaps.
- `AR-06-07` — [prioritized_hotspot_map_spec.md](architecture-hotspots/prioritized_hotspot_map_spec.md) — Prioritized hotspot map.

### 07. Architecture debt and smells

Turn structural symptoms into evidenced architectural findings, accounting for intentional tradeoffs and the cost of remediation.

- `AR-07-01` — [god_components_spec.md](architecture-debt-and-smells/god_components_spec.md) — God components.
- `AR-07-02` — [dependency_cycles_spec.md](architecture-debt-and-smells/dependency_cycles_spec.md) — Dependency cycles as architectural debt.
- `AR-07-03` — [layer_violations_spec.md](architecture-debt-and-smells/layer_violations_spec.md) — Layer violations as architectural debt.
- `AR-07-04` — [excessive_centralization_spec.md](architecture-debt-and-smells/excessive_centralization_spec.md) — Excessive centralization.
- `AR-07-05` — [leaky_abstractions_spec.md](architecture-debt-and-smells/leaky_abstractions_spec.md) — Leaky abstractions.
- `AR-07-06` — [duplicate_mechanisms_spec.md](architecture-debt-and-smells/duplicate_mechanisms_spec.md) — Duplicate mechanisms.
- `AR-07-07` — [ownership_boundary_mismatches_spec.md](architecture-debt-and-smells/ownership_boundary_mismatches_spec.md) — Ownership boundary mismatches.
- `AR-07-08` — [fan_in_and_fan_out_spec.md](architecture-debt-and-smells/fan_in_and_fan_out_spec.md) — Fan-in and fan-out.
- `AR-07-09` — [architecture_drift_spec.md](architecture-debt-and-smells/architecture_drift_spec.md) — Architecture drift.

### 08. Data and state ownership

Make ownership, access, durability, consistency, and failure behavior explicit for important data and operational state.

- `AR-08-01` — [data_ownership_spec.md](data-and-state-ownership/data_ownership_spec.md) — Data ownership.
- `AR-08-02` — [data_writers_spec.md](data-and-state-ownership/data_writers_spec.md) — Data writers.
- `AR-08-03` — [data_readers_spec.md](data-and-state-ownership/data_readers_spec.md) — Data readers.
- `AR-08-04` — [sources_of_truth_spec.md](data-and-state-ownership/sources_of_truth_spec.md) — Sources of truth.
- `AR-08-05` — [cache_topology_and_invalidation_spec.md](data-and-state-ownership/cache_topology_and_invalidation_spec.md) — Cache topology and invalidation.
- `AR-08-06` — [durable_vs_ephemeral_state_spec.md](data-and-state-ownership/durable_vs_ephemeral_state_spec.md) — Durable versus ephemeral state.
- `AR-08-07` — [consistency_and_disagreement_spec.md](data-and-state-ownership/consistency_and_disagreement_spec.md) — Consistency and disagreement.
- `AR-08-08` — [partial_failure_behavior_spec.md](data-and-state-ownership/partial_failure_behavior_spec.md) — Partial-failure behavior of state.
- `AR-08-09` — [crud_and_ownership_matrix_spec.md](data-and-state-ownership/crud_and_ownership_matrix_spec.md) — CRUD and ownership matrix.

### 09. Critical workflow analysis

Explain important end-to-end behavior and the architectural constraints hidden within execution sequences.

- `AR-09-01` — [end_to_end_workflow_spec.md](critical-workflow-analysis/end_to_end_workflow_spec.md) — End-to-end workflow.
- `AR-09-02` — [critical_path_spec.md](critical-workflow-analysis/critical_path_spec.md) — Critical workflow path.
- `AR-09-03` — [failure_points_spec.md](critical-workflow-analysis/failure_points_spec.md) — Workflow failure points.
- `AR-09-04` — [cross_boundary_calls_spec.md](critical-workflow-analysis/cross_boundary_calls_spec.md) — Cross-boundary calls.
- `AR-09-05` — [state_transitions_spec.md](critical-workflow-analysis/state_transitions_spec.md) — Workflow state transitions.
- `AR-09-06` — [retry_and_idempotency_behavior_spec.md](critical-workflow-analysis/retry_and_idempotency_behavior_spec.md) — Retry and idempotency behavior.
- `AR-09-07` — [hidden_workflow_dependencies_spec.md](critical-workflow-analysis/hidden_workflow_dependencies_spec.md) — Hidden workflow dependencies.

### 10. Reliability and failure architecture

Assess how architectural boundaries, state, and recovery mechanisms behave under explicitly scoped failure scenarios.

- `AR-10-01` — [single_points_of_failure_spec.md](reliability-and-failure-architecture/single_points_of_failure_spec.md) — Single points of failure.
- `AR-10-02` — [failure_cascades_spec.md](reliability-and-failure-architecture/failure_cascades_spec.md) — Failure cascades.
- `AR-10-03` — [dependency_unavailability_spec.md](reliability-and-failure-architecture/dependency_unavailability_spec.md) — Dependency unavailability.
- `AR-10-04` — [state_inconsistency_risks_spec.md](reliability-and-failure-architecture/state_inconsistency_risks_spec.md) — State inconsistency risks.
- `AR-10-05` — [restart_and_retry_behavior_spec.md](reliability-and-failure-architecture/restart_and_retry_behavior_spec.md) — Restart and retry behavior.
- `AR-10-06` — [recovery_mechanism_gaps_spec.md](reliability-and-failure-architecture/recovery_mechanism_gaps_spec.md) — Recovery mechanism gaps.

### 11. Scalability ceilings

Identify plausible capacity limits under explicit workload assumptions and distinguish measured ceilings from unverified scaling hypotheses.

- `AR-11-01` — [first_limiting_component_spec.md](scalability-ceilings/first_limiting_component_spec.md) — First limiting component.
- `AR-11-02` — [bottleneck_mechanisms_spec.md](scalability-ceilings/bottleneck_mechanisms_spec.md) — Bottleneck mechanisms.
- `AR-11-03` — [resource_capacity_constraints_spec.md](scalability-ceilings/resource_capacity_constraints_spec.md) — Resource capacity constraints.
- `AR-11-04` — [centralized_bottlenecks_spec.md](scalability-ceilings/centralized_bottlenecks_spec.md) — Centralized bottlenecks.
- `AR-11-05` — [shared_resource_contention_spec.md](scalability-ceilings/shared_resource_contention_spec.md) — Shared resource contention.
- `AR-11-06` — [tenfold_and_hundredfold_growth_scenarios_spec.md](scalability-ceilings/tenfold_and_hundredfold_growth_scenarios_spec.md) — Tenfold and hundredfold growth scenarios.

### 12. Performance and latency architecture

Focus on structural sources of delay and resource work rather than unprioritized line-level micro-optimization.

- `AR-12-01` — [critical_latency_paths_spec.md](performance-and-latency-architecture/critical_latency_paths_spec.md) — Critical latency paths.
- `AR-12-02` — [serial_dependencies_spec.md](performance-and-latency-architecture/serial_dependencies_spec.md) — Serial dependencies.
- `AR-12-03` — [excessive_remote_calls_spec.md](performance-and-latency-architecture/excessive_remote_calls_spec.md) — Excessive remote calls.
- `AR-12-04` — [chatty_service_boundaries_spec.md](performance-and-latency-architecture/chatty_service_boundaries_spec.md) — Chatty service boundaries.
- `AR-12-05` — [data_movement_spec.md](performance-and-latency-architecture/data_movement_spec.md) — Data movement.
- `AR-12-06` — [synchronization_points_spec.md](performance-and-latency-architecture/synchronization_points_spec.md) — Synchronization points.

### 13. Security and trust boundaries

Describe architectural security exposure and control boundaries without implying that an architecture review is a complete security audit.

- `AR-13-01` — [trust_boundary_map_spec.md](security-and-trust-boundaries/trust_boundary_map_spec.md) — Trust boundary map.
- `AR-13-02` — [privilege_concentration_spec.md](security-and-trust-boundaries/privilege_concentration_spec.md) — Privilege concentration.
- `AR-13-03` — [sensitive_data_flows_spec.md](security-and-trust-boundaries/sensitive_data_flows_spec.md) — Sensitive-data flows.
- `AR-13-04` — [authentication_and_authorization_boundaries_spec.md](security-and-trust-boundaries/authentication_and_authorization_boundaries_spec.md) — Authentication and authorization boundaries.
- `AR-13-05` — [dependency_and_security_exposure_spec.md](security-and-trust-boundaries/dependency_and_security_exposure_spec.md) — Dependency and security exposure.
- `AR-13-06` — [security_blast_radius_spec.md](security-and-trust-boundaries/security_blast_radius_spec.md) — Security blast radius.

### 14. Architecture evolution

Compare meaningful architectural changes over time using compatible snapshots and clearly defined history windows.

- `AR-14-01` — [coupling_trends_spec.md](architecture-evolution/coupling_trends_spec.md) — Coupling trends.
- `AR-14-02` — [hotspot_growth_spec.md](architecture-evolution/hotspot_growth_spec.md) — Hotspot growth.
- `AR-14-03` — [boundary_deterioration_spec.md](architecture-evolution/boundary_deterioration_spec.md) — Boundary deterioration.
- `AR-14-04` — [responsibility_accumulation_spec.md](architecture-evolution/responsibility_accumulation_spec.md) — Responsibility accumulation.
- `AR-14-05` — [technical_debt_trends_spec.md](architecture-evolution/technical_debt_trends_spec.md) — Technical debt trends.
- `AR-14-06` — [architecture_diff_between_releases_spec.md](architecture-evolution/architecture_diff_between_releases_spec.md) — Architecture diff between releases.

### 15. Team and architecture alignment

Identify where technical boundaries and actual accountability support or obstruct coordinated delivery without evaluating individual employees.

- `AR-15-01` — [code_ownership_spec.md](team-and-architecture-alignment/code_ownership_spec.md) — Code ownership.
- `AR-15-02` — [team_ownership_spec.md](team-and-architecture-alignment/team_ownership_spec.md) — Team ownership.
- `AR-15-03` — [team_to_service_boundary_alignment_spec.md](team-and-architecture-alignment/team_to_service_boundary_alignment_spec.md) — Team-to-service boundary alignment.
- `AR-15-04` — [cross_team_change_patterns_spec.md](team-and-architecture-alignment/cross_team_change_patterns_spec.md) — Cross-team change patterns.
- `AR-15-05` — [shared_subsystem_coordination_spec.md](team-and-architecture-alignment/shared_subsystem_coordination_spec.md) — Shared subsystem coordination.

### 16. Decision and what-if analysis

Evaluate concrete architectural changes as bounded scenarios, with dependencies, tradeoffs, and uncertainty made explicit.

- `AR-16-01` — [service_split_scenarios_spec.md](decision-and-what-if-analysis/service_split_scenarios_spec.md) — Service split scenarios.
- `AR-16-02` — [safe_module_extraction_spec.md](decision-and-what-if-analysis/safe_module_extraction_spec.md) — Safe module extraction.
- `AR-16-03` — [technology_replacement_spec.md](decision-and-what-if-analysis/technology_replacement_spec.md) — Technology replacement.
- `AR-16-04` — [workload_relocation_spec.md](decision-and-what-if-analysis/workload_relocation_spec.md) — Workload relocation.
- `AR-16-05` — [component_elimination_spec.md](decision-and-what-if-analysis/component_elimination_spec.md) — Component elimination.
- `AR-16-06` — [microservice_independence_spec.md](decision-and-what-if-analysis/microservice_independence_spec.md) — Microservice independence.

### 17. Alternative target architectures

Offer comparable intervention options rather than a single prescriptive redesign, including the consequences of retaining the current architecture.

- `AR-17-01` — [minimal_intervention_option_spec.md](alternative-target-architectures/minimal_intervention_option_spec.md) — Minimal intervention option.
- `AR-17-02` — [boundary_cleanup_option_spec.md](alternative-target-architectures/boundary_cleanup_option_spec.md) — Boundary cleanup option.
- `AR-17-03` — [architectural_restructuring_option_spec.md](alternative-target-architectures/architectural_restructuring_option_spec.md) — Architectural restructuring option.
- `AR-17-04` — [option_tradeoffs_and_selection_spec.md](alternative-target-architectures/option_tradeoffs_and_selection_spec.md) — Option tradeoffs and selection.

### 18. Concrete prioritized recommendations

Convert findings into a short, traceable set of actions with impact, effort, priority, and verifiable outcomes.

- `AR-18-01` — [finding_statement_spec.md](prioritized-recommendations/finding_statement_spec.md) — Finding statement.
- `AR-18-02` — [supporting_evidence_spec.md](prioritized-recommendations/supporting_evidence_spec.md) — Supporting evidence for a recommendation.
- `AR-18-03` — [impact_assessment_spec.md](prioritized-recommendations/impact_assessment_spec.md) — Impact assessment.
- `AR-18-04` — [recommended_action_spec.md](prioritized-recommendations/recommended_action_spec.md) — Recommended action.
- `AR-18-05` — [effort_estimate_spec.md](prioritized-recommendations/effort_estimate_spec.md) — Effort estimate.
- `AR-18-06` — [validation_plan_spec.md](prioritized-recommendations/validation_plan_spec.md) — Validation plan.
- `AR-18-07` — [priority_and_ordering_spec.md](prioritized-recommendations/priority_and_ordering_spec.md) — Priority and ordering.

### 19. Sequenced migration and refactoring roadmap

Turn selected recommendations into a safe sequence with explicit dependencies, compatibility windows, validation gates, and rollback constraints.

- `AR-19-01` — [migration_stages_and_milestones_spec.md](sequenced-migration-roadmap/migration_stages_and_milestones_spec.md) — Migration stages and milestones.
- `AR-19-02` — [contract_establishment_spec.md](sequenced-migration-roadmap/contract_establishment_spec.md) — Contract establishment.
- `AR-19-03` — [state_isolation_spec.md](sequenced-migration-roadmap/state_isolation_spec.md) — State isolation.
- `AR-19-04` — [read_path_migration_spec.md](sequenced-migration-roadmap/read_path_migration_spec.md) — Read-path migration.
- `AR-19-05` — [write_path_migration_spec.md](sequenced-migration-roadmap/write_path_migration_spec.md) — Write-path migration.
- `AR-19-06` — [service_extraction_and_cutover_spec.md](sequenced-migration-roadmap/service_extraction_and_cutover_spec.md) — Service extraction and cutover.
- `AR-19-07` — [recommendation_dependencies_and_safe_order_spec.md](sequenced-migration-roadmap/recommendation_dependencies_and_safe_order_spec.md) — Recommendation dependencies and safe order.
- `AR-19-08` — [rollback_and_exit_criteria_spec.md](sequenced-migration-roadmap/rollback_and_exit_criteria_spec.md) — Rollback and exit criteria.

### 20. Business impact

Translate architectural mechanisms into decision-relevant outcomes, keeping measured results, estimates, and hypotheses separate.

- `AR-20-01` — [change_lead_time_spec.md](business-impact/change_lead_time_spec.md) — Change lead time.
- `AR-20-02` — [release_risk_spec.md](business-impact/release_risk_spec.md) — Release risk.
- `AR-20-03` — [incident_likelihood_spec.md](business-impact/incident_likelihood_spec.md) — Incident likelihood.
- `AR-20-04` — [developer_coordination_cost_spec.md](business-impact/developer_coordination_cost_spec.md) — Developer coordination cost.
- `AR-20-05` — [infrastructure_cost_spec.md](business-impact/infrastructure_cost_spec.md) — Infrastructure cost.
- `AR-20-06` — [scaling_capability_spec.md](business-impact/scaling_capability_spec.md) — Scaling capability.
- `AR-20-07` — [hiring_and_onboarding_complexity_spec.md](business-impact/hiring_and_onboarding_complexity_spec.md) — Hiring and onboarding complexity.
- `AR-20-08` — [independent_deployment_spec.md](business-impact/independent_deployment_spec.md) — Independent deployment.

### 21. Evidence and confidence

Make every material claim auditable, scoped, and explicit about what is observed, inferred, assumed, or not known.

- `AR-21-01` — [source_code_evidence_spec.md](evidence-and-confidence/source_code_evidence_spec.md) — Source-code evidence.
- `AR-21-02` — [runtime_trace_evidence_spec.md](evidence-and-confidence/runtime_trace_evidence_spec.md) — Runtime trace evidence.
- `AR-21-03` — [dependency_edge_evidence_spec.md](evidence-and-confidence/dependency_edge_evidence_spec.md) — Dependency-edge evidence.
- `AR-21-04` — [historical_commit_evidence_spec.md](evidence-and-confidence/historical_commit_evidence_spec.md) — Historical commit evidence.
- `AR-21-05` — [incident_and_test_evidence_spec.md](evidence-and-confidence/incident_and_test_evidence_spec.md) — Incident and test evidence.
- `AR-21-06` — [confidence_assessment_spec.md](evidence-and-confidence/confidence_assessment_spec.md) — Confidence assessment.
- `AR-21-07` — [counterevidence_and_uncertainty_spec.md](evidence-and-confidence/counterevidence_and_uncertainty_spec.md) — Counterevidence and uncertainty.
- `AR-21-08` — [claim_to_evidence_traceability_spec.md](evidence-and-confidence/claim_to_evidence_traceability_spec.md) — Claim-to-evidence traceability.

### 22. Unknowns and verification tasks

Make analysis limits explicit and convert consequential uncertainty into concrete, bounded information-gathering work.

- `AR-22-01` — [undetermined_findings_spec.md](unknowns-and-verification-tasks/undetermined_findings_spec.md) — Undetermined findings.
- `AR-22-02` — [missing_runtime_information_spec.md](unknowns-and-verification-tasks/missing_runtime_information_spec.md) — Missing runtime information.
- `AR-22-03` — [assumptions_register_spec.md](unknowns-and-verification-tasks/assumptions_register_spec.md) — Assumptions register.
- `AR-22-04` — [next_measurements_and_verification_tasks_spec.md](unknowns-and-verification-tasks/next_measurements_and_verification_tasks_spec.md) — Next measurements and verification tasks.

### 23. Implementation-ready work packages

Express approved or proposed improvements as bounded tasks that a human engineer or coding agent can execute and verify under explicit authority.

- `AR-23-01` — [task_goal_spec.md](implementation-ready-work-packages/task_goal_spec.md) — Task goal.
- `AR-23-02` — [relevant_files_and_components_spec.md](implementation-ready-work-packages/relevant_files_and_components_spec.md) — Relevant files and components.
- `AR-23-03` — [architectural_constraints_spec.md](implementation-ready-work-packages/architectural_constraints_spec.md) — Architectural constraints.
- `AR-23-04` — [non_goals_spec.md](implementation-ready-work-packages/non_goals_spec.md) — Non-goals.
- `AR-23-05` — [migration_steps_spec.md](implementation-ready-work-packages/migration_steps_spec.md) — Migration steps within a work package.
- `AR-23-06` — [required_tests_spec.md](implementation-ready-work-packages/required_tests_spec.md) — Required tests.
- `AR-23-07` — [acceptance_criteria_spec.md](implementation-ready-work-packages/acceptance_criteria_spec.md) — Acceptance criteria.
- `AR-23-08` — [coding_agent_handoff_spec.md](implementation-ready-work-packages/coding_agent_handoff_spec.md) — Coding-agent handoff.
