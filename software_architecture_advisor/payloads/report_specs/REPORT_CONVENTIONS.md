# Shared report conventions

These conventions apply to every aspect specification in this archive. Each
specification describes **content to produce in a future architecture report**;
it is not a completed finding or permission to change a system.

## 1. Scope and evidence before conclusions

Every report must identify the reviewed system, intended audience, customer
questions, relevant goals, repositories and immutable versions, environments,
analysis date, history windows, and explicitly excluded areas. Record the tools,
methods, supported languages, and known extraction limitations when applicable.

Separate source structure, configured deployment, and observed runtime behavior.
A development manifest is not proof of production topology. A reachable code path
is not proof that it executes. An absent graph edge is not proof that a dependency
does not exist, especially when dynamic behavior or external consumers are out of
scope.

Use the 23 sections as a content catalog, not an obligation to invent an answer
for every question. Evaluate each aspect, then state its applicability and
coverage. Unsupported capacity, reliability, security, or business claims should
become bounded hypotheses and verification tasks.

## 2. Content contract for each aspect

Every aspect file contains the customer question, what to include, why it
matters, evidence to use, expected report output, and completion checks. Those
fields specify the content; they do not mandate a particular analysis tool,
programming language, or storage format.

A populated report item should carry its scope, relevant entity IDs, conclusion,
evidence links, reasoning summary, confidence, limitations, and next action where
one is warranted. Provide a useful conclusion before presenting supporting
metrics or a diagram. Keep explanation proportionate to the decision.

## 3. Applicability and coverage are different

Record **applicability** as `applicable`, `not_applicable`, or `undetermined`.
Record **coverage** separately as `complete_for_stated_scope`, `partial`,
`not_analyzed`, or `blocked`.

For individual outputs, use precise outcome descriptions such as
`finding_identified`, `no_finding_in_analyzed_scope`, or `undetermined`.
Do not turn `not_analyzed`, `blocked`, or `undetermined` into a positive health
assessment. A not-applicable designation needs a reason, such as no service
extraction being selected. A blocked item needs the missing input or access
condition, not a fabricated result.

When evidence is missing, report what is known, what cannot yet be concluded,
the decision affected, and the smallest useful verification task. Completion for
a specification means that its requirements and limitations are addressed; it
does not require a positive finding or a recommendation to change something.

## 4. Separate observation from inference

Use explicit claim types:

| Claim type | Meaning |
| --- | --- |
| Observed | Directly supported by a reviewed artifact or measurement, within a stated scope. |
| Derived | Calculated or reconstructed from identified evidence using a described method. |
| Inferred | An interpretation supported by evidence, with alternatives or gaps still relevant. |
| Assumed | A premise adopted for a scenario or estimate but not established as fact. |
| Proposed | A target, action, threshold, policy, or design for consideration. |

A recommendation is proposed even when its underlying problem is observed. A
runtime inference should not silently become an observed fact in an executive
summary. Present expected improvements as hypotheses or estimates until validated.

## 5. Traceability and stable identifiers

Use immutable artifact references wherever possible. Suggested report IDs are
`C-001` for a claim, `E-001` for evidence, `F-001` for a finding, `R-001` for a
recommendation, `A-001` for an assumption, `V-001` for a verification task,
`M-001` for a migration stage, and `W-001` for a work package. Component and data
entity IDs should also be stable within a report and between comparable releases.
These report IDs differ from the catalog specification IDs such as `AR-01-01`.

The traceability chain is:

```text
Reviewed artifact -> evidence -> claim -> finding -> recommendation
                                                -> verification task
Recommendation -> decision -> migration stage -> work package -> validation evidence
```

Source evidence needs a real repository, immutable commit, file and symbol or
line locator. Runtime evidence needs environment, time or window, workload,
trace or log identity, and sampling limitations. History evidence needs actual
change IDs and the filtering method. Test evidence must distinguish a test that
exists from a test that ran and its actual result.

Never invent counts, paths, line numbers, timestamps, benchmark results, test
outcomes, or citations. If a locator cannot be provided, state that limitation
and lower the supported scope of the claim. Several summaries of one source do
not count as independent corroboration.

## 6. Confidence, impact, and priority

Assess confidence per material claim, with a brief rationale:

| Confidence | Default interpretation |
| --- | --- |
| High | Direct, reproducible evidence supports the claim within the stated scope, with no unresolved material contradiction. |
| Medium | The evidence supports the interpretation, but meaningful coverage gaps, environmental assumptions, or indirect steps remain. |
| Low | The claim is a plausible hypothesis with limited, indirect, or conflicting support. |
| Insufficient evidence | A responsible conclusion cannot yet be made. Record a verification task instead. |

These labels are not calibrated probabilities. They describe the support for a
claim, not the severity of a risk, the importance of a component, or a coding
model's self-reported certainty.

Report impact, urgency, effort, and confidence separately. A high-impact,
low-confidence concern may justify urgent verification rather than an urgent
rewrite. Explain prioritization and any weighting used. Do not create an opaque
overall architecture score or treat missing measurements as zero risk.

## 7. Metrics, history, and forecasts

For every metric, state its definition, unit, granularity, observation window,
denominator, exclusions, extraction method, and known missing data. Historical
comparisons need compatible snapshots, rename handling, and stable component
mapping. Explain changes in methodology before comparing results.

A dependency path establishes possible exposure, not certain breakage. Co-change
is an association, not proof of causation. Centrality is a structural measure,
not a measurement of production traffic or incident likelihood. Complexity and
churn are signals to interpret, not automatic verdicts.

Label numbers as measured, calculated, estimated, assumed, or proposed. State
formulas and inputs for estimates. Keep 10× and 100× growth scenarios conditional
on explicit workload dimensions. Without runtime measurements, provide capacity
hypotheses and a validation plan, not fabricated throughput or latency results.
Do not add independent stage percentiles to claim an end-to-end percentile.

## 8. Business impact and cost

Connect each business claim to a technical mechanism and a defined outcome.
Separate engineering effort, elapsed lead time, recurring operational cost,
transition cost, and expected business benefit. Use customer-provided or
separately verified, dated prices and usage for cost estimates. Show assumptions,
ranges, sensitivity, and excluded costs.

Do not invent customer revenue, bills, service obligations, staffing, or incident
probabilities. Avoid counting one delay as multiple independent benefits. A
qualitative assessment with a clear mechanism is preferable to unsupported
numerical precision. Recommendations are conditional on the customer's supplied
goals, constraints, and decision authority.

## 9. Output and visualization rules

Use small, task-focused views: a component map for understanding, a sequence for a
workflow, a CRUD matrix for data authority, an impact slice for a proposed change,
a boundary matrix for exceptions, or a before/after view for a decision. Visuals
are supporting evidence, not the main deliverable.

Every visual needs a question, scope, legend, node and edge meaning, version or
window, and explanation of the actionable result. Distinguish observed, inferred,
and proposed elements. Do not produce an unlabeled whole-system graph merely to
show that analysis was performed. Provide an accessible table or narrative for
the significant conclusion.

## 10. Recommendations and implementation

A recommendation should contain the following information, without requiring an
identical layout for every finding:

```text
Finding and current behavior
Evidence and counterevidence
Impact and affected scope
Recommended action and alternatives
Effort, constraints, prerequisites, and risks
Validation method and success conditions
Priority, owner status, and next decision
```

Migration plans must describe intermediate states, mixed-version behavior, data
authority, gates, and rollback or forward-repair limitations. Reverting a binary
does not necessarily reverse data mutations or external effects. Service
extraction is one possible intervention, not the default destination.

Work packages should be usable by a human or coding agent with bounded scope.
They must state baseline, allowed actions, constraints, non-goals, actual context,
required tests, acceptance evidence, and stop conditions. Proposed tasks are not
authorization to deploy, conduct disruptive tests, modify production data,
access new sources, expose secrets, or expand scope.

## 11. Privacy, security, and organizational boundaries

Minimize and redact sensitive source excerpts, payloads, identities, and
operational details. Do not include secret values. Use team or role-level
ownership where possible and distinguish formal accountability from edit history.
Do not infer individual performance or assign blame from repository activity.

An architecture review is not a penetration test, legal opinion, regulatory
certification, or guarantee that vulnerabilities are absent. A trust-boundary or
security-blast-radius view is a defensive model whose assumptions must be stated.
Any live security findings or technology comparisons require actual scoped and
dated evidence, not facts invented while filling out a template.

## 12. Canonical findings and repeated topics

Several sections intentionally look at the same subject from different angles.
Maintain one canonical finding and reuse its ID:

| Diagnostic content | Decision or application content |
| --- | --- |
| Hidden coupling: circular dependencies | Architecture debt: whether a cycle warrants remediation. |
| Hidden coupling: cross-layer dependencies | Architecture debt: practical cost and enforcement of layer rules. |
| Data ownership and consistency | Reliability: correctness under specific failure scenarios. |
| Workflow dependency path | Performance: observed or hypothesized contribution to latency. |
| Report-wide co-change | Change blast radius: additional review targets for one proposed change. |
| Current hotspot signals | Evolution: comparable trends across time. |
| Microservice independence | Business impact: delivery and coordination consequences. |
| Recommendation validation | Work package: executable tests and acceptance evidence. |

Do not duplicate the same issue as several independent risks or savings. Link
the underlying evidence and explain the distinct customer question each section
answers.

## 13. Suggested production order

The archive follows the report's reading order, not the order of analysis.
Establish scope, evidence, assumptions, and coverage first. Reconstruct the
system, data, and critical workflows. Analyze structural and historical signals,
reliability, security, capacity, performance, and ownership as evidence permits.
Then evaluate change scenarios, business impact, alternatives, recommendations,
migration, and work packages. Write the executive brief last so that its claims
and priorities match the detailed evidence.

## 14. Report-level acceptance checklist

- All 23 sections have an applicability and coverage decision; omitted aspects
  have a stated reason rather than invented findings.
- Every material claim has a real supporting locator or is explicitly labeled
  inferred, assumed, proposed, or undetermined with an appropriate limitation.
- Key findings have a consequence, next action, confidence rationale, and relevant
  counterevidence; priority is not confused with certainty.
- Recommended work traces to findings, alternatives, dependencies, validation,
  and approved scope; migration plans account for state and reversibility.
- Measurements and estimates expose their basis; no tests, operational checks,
  customer research, or source access are claimed unless actually performed.
- Summaries, tables, diagrams, and implementation tasks use consistent component,
  finding, and recommendation IDs and do not double-count one underlying issue.
