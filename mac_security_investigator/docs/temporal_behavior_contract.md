# Local Mac Security Investigator
## Cross-Run Temporal Behavioral Graph Specification

**Version:** 1.0  
**Date:** October 7, 2026  
**Status:** Proposed product and engineering specification  
**Scope:** Local, Mac-only, retrospective, read-only, detection and evidence only  
**Integration boundary:** Use the existing evidence, graph, retrieval, and execution infrastructure. This specification defines behavioral semantics and correctness contracts; it does not select inference models, graph-building tools, databases, or frameworks.

> **The product is a persistent temporal investigator, not a collection of independent security scans. Each run contributes observations to a shared history. The core engine connects those observations, identifies changes and recurring behavioral sequences, and revises evidence-backed investigations over time.**

---

## Contents

1. [Purpose and product contract](#1-purpose-and-product-contract)
2. [Scope and operating boundaries](#2-scope-and-operating-boundaries)
3. [Foundational concepts](#3-foundational-concepts)
4. [Evidence capabilities and Mac-specific limits](#4-evidence-capabilities-and-mac-specific-limits)
5. [Graph semantics and identity](#5-graph-semantics-and-identity)
6. [Temporal semantics](#6-temporal-semantics)
7. [Coverage and negative evidence](#7-coverage-and-negative-evidence)
8. [Cross-run reconciliation](#8-cross-run-reconciliation)
9. [Incremental analysis lifecycle](#9-incremental-analysis-lifecycle)
10. [Temporal behavioral analysis](#10-temporal-behavioral-analysis)
11. [Detection pattern contracts](#11-detection-pattern-contracts)
12. [Worked multi-run investigation](#12-worked-multi-run-investigation)
13. [Evidence-backed reasoning and assessment](#13-evidence-backed-reasoning-and-assessment)
14. [Persistent cases and finding revisions](#14-persistent-cases-and-finding-revisions)
15. [Functional integration contracts](#15-functional-integration-contracts)
16. [Investigation experience](#16-investigation-experience)
17. [Safety, privacy, and evidence integrity](#17-safety-privacy-and-evidence-integrity)
18. [Evaluation and acceptance criteria](#18-evaluation-and-acceptance-criteria)
19. [Delivery sequence and definition of done](#19-delivery-sequence-and-definition-of-done)
20. [Sources and grounding notes](#20-sources-and-grounding-notes)

---

## 1. Purpose and product contract

### 1.1 Primary question

The investigator must answer:

> **Across the evidence collected so far, which connected sequences of behavior deserve attention, how did they develop over time, and which observations support or challenge that interpretation?**

The primary unit of analysis is an **evidence-backed temporal behavioral subgraph**. It may span several collection runs, application executions, login sessions, or machine restarts. A scan boundary must not become an artificial boundary of an investigation.

### 1.2 Essential capabilities

The product must connect evidence across runs to recognize:

- **Progression:** separate observations become meaningful when joined into a time-ordered sequence.
- **Change:** a previously observed entity changes target, content, execution context, or relationships.
- **Recurrence:** a behavior happens again in a distinct occurrence, rather than merely appearing in another scan.
- **Reinterpretation:** newly acquired historical evidence strengthens, weakens, or overturns an existing explanation.

These capabilities must work even when no individual scan contains the complete sequence.

### 1.3 User-facing promise

> **“I connect the evidence from your Mac over time, investigate suspicious behavior, and show what supports the finding—including what remains unknown.”**

Do not promise complete historical reconstruction, comprehensive malware detection, continuous protection, proof that the Mac is clean, or proof that no data was accessed.

### 1.4 Non-negotiable principles

**P-01 — History belongs to the machine investigation, not to a scan.** A scan is an acquisition boundary, not a separate world.

**P-02 — Observation is not occurrence.** Seeing a file in three scans does not mean it was created, executed, or installed three times.

**P-03 — Relationships require evidence.** Shared names, nearby timestamps, or graph connectivity alone do not establish causation.

**P-04 — Uncertainty survives every transformation.** Missing identity, imprecise time, incomplete coverage, and disputed attribution must remain visible in matching, ranking, and presentation.

**P-05 — Conclusions are revisable; evidence history is preserved.** New knowledge can change a case without silently rewriting its previous reports.

**P-06 — No corrective action.** The product detects, reconstructs, explains, and presents evidence. It does not fix the machine.

---

## 2. Scope and operating boundaries

### 2.1 In scope

User-initiated analysis of existing Mac artifacts and historical records; durable local evidence history; cross-run identity resolution; state comparison; temporal pattern matching; retrospective graph queries; evidence-backed cases; and local report export.

The initial source set should emphasize existing system records and startup/application state. Additional sources, such as browser records, are independently permissioned inputs—not prerequisites for the architecture.

### 2.2 Out of scope

Continuous event subscription, live interception, background surveillance between scans, real-time prevention, file quarantine, process termination, network blocking, changing startup settings, executing suspicious files, credential extraction, automatic remediation, and cross-machine campaign correlation.

Selecting or replacing the existing graph infrastructure is also out of scope.

### 2.3 Meaning of read-only

The investigator must not intentionally modify inspected source artifacts or security configuration. It may write evidence copies, manifests, indexes, checkpoints, findings, and reports to its own local workspace.

“Read-only” is an application behavior contract, not a promise of a physically write-free forensic acquisition: running software on the Mac may itself generate system activity. Record the investigator's acquisition interval and identifiable activity so that it is not confused with the behavior under investigation.

### 2.4 Meaning of offline and retrospective

**Retrospective** means reasoning from existing records rather than watching actions as they occur. **Local/offline-capable** means core analysis must work without sending evidence to external services or requiring network access. The Mac need not be shut down or disconnected during a scan.

The system is idle between user-initiated runs. Its persistent state is investigation memory, not a live sensor.

---

## 3. Foundational concepts

| Concept | Required meaning |
|---|---|
| Machine | The locally scoped device whose evidence is being investigated. |
| Host epoch | A continuity boundary for an OS installation or reconstructed machine history. A restore or ambiguous identity discontinuity may require a new epoch rather than silently merging histories. |
| Collection run / scan | One bounded attempt to acquire existing evidence, with source-level acquisition times, scope, and results. |
| Analysis run | One evaluation against a fixed evidence/graph revision and versioned policies. It may consume several scans and need not acquire new evidence. |
| Execution instance | One particular process or application execution. It is not the same thing as a scan or an installed application. |
| Boot or login session | An optional, evidence-backed boundary used to distinguish execution contexts. Unknown session identity must remain unknown. |
| Observation | A statement that a source contained a record or a state was observed during acquisition. |
| Event | An occurrence supported by an event-bearing source, with its own temporal semantics. |
| State observation | Evidence of a property at acquisition or at an explicitly supported historical time. It is not automatically an event. |
| Entity/version | A persistent identity and one particular content or configuration state of that identity. |
| Behavioral episode | A connected set of distinct events and state transitions that may implement one activity. Membership can be uncertain. |
| Case | A durable investigation of a behavioral concern, with versioned findings, evidence, alternatives, and assessment history. |
| Graph revision | A committed, reproducible view of normalized evidence and accepted derivations. |

An application observed during ten scans can still represent one installation, two content versions, and an unknown number of executions. Keep these cardinalities separate.

---

## 4. Evidence capabilities and Mac-specific limits

### 4.1 Platform grounding

Apple's logging documentation describes both retained on-device logs and in-memory logging; retention depends on logging level and storage behavior. The product must discover actual available history rather than assume a fixed number of days. [R1]

Some log values are private or redacted. A missing value must not be reconstructed as a fact merely because a likely value exists elsewhere. [R1]

Login items and background applications are normal macOS features, including for updating and synchronization. Their existence alone must not be classified as malicious. [R2]

Launch agents and daemons are also normal service mechanisms. A startup definition is evidence of configuration; the detector must separately establish whether a particular execution occurred. [R3]

Apple describes code-signing, notarization, provenance, and runtime protections as distinct checks. Record the exact available check and its observation time rather than reducing these properties to one timeless “trusted” boolean. [R4]

These facts motivate the contracts below. Actual source support must be validated on each supported macOS version; this specification does not assume every source exposes every event type.

### 4.2 Evidence capability matrix

| Input class, when available | Permitted use | Unsupported leap to avoid |
|---|---|---|
| Historical system or application event record | Extract the action and identifiers explicitly represented by that record. | Assume it is a complete process, file-access, or network audit. |
| Current startup configuration | Record configured target, arguments, scope, and captured configuration version. | Claim the target ran, identify who created it, or assign an exact creation time. |
| Repeated startup snapshots | Identify differences between comparable observations. | Treat continuous presence or the precise change moment as directly observed. |
| File and application metadata | Relate paths, content versions, available provenance, and captured properties. | Treat a path as permanent identity or a metadata timestamp as unquestionable chronology. |
| Installation or download records | Support the installation/download semantics actually present in the source. | Infer subsequent execution, ownership of every nearby file, or malicious intent. |
| Historical execution evidence | Bind an execution to the identifiers and executable version the record actually supports. | Reconstruct a complete process tree from unrelated messages or a reused process number. |
| Historical connection evidence | Record the connection or request described by the source, with available attribution. | Infer data exfiltration, message contents, or all destinations contacted. |
| Access or authorization records | Separate requested, denied, granted, and completed actions. | Equate permission with actual reading of sensitive data. |
| Source acquisition failure | Record a visibility gap. | Treat the source's contents as empty or the missing evidence as benign. |

### 4.3 Two useful operating modes

**Snapshot-rich, event-poor:** the investigator can still analyze persistent configuration evolution, target replacement, identity changes, and observed return after absence. Findings must remain about state and change, not invented execution chains.

**Historical-event-enriched:** available event records allow execution episodes, ordered action chains, and recurrence analysis. Activate each behavior predicate only when its required source capability is present.

The engine must support both modes without presenting the first as the second.

---

## 5. Graph semantics and identity

### 5.1 Separate semantic layers

The existing graph infrastructure must expose these logical distinctions, regardless of physical representation:

```text
Immutable evidence and source receipts
                 |
                 v
Observations, event records, and state observations
                 |
                 v
Entity identity, versions, and supported relationships
                 |
                 v
Temporal changes, behavioral episodes, pattern witnesses
                 |
                 v
Case hypotheses, assessments, and report revisions
```

An AI-generated explanation must never become the source evidence for its own claims.

### 5.2 Identity contract

Each durable entity must have an identity that survives another scan. Identity is separate from its display name, current path, content version, and observation run.

The entity layer must distinguish, where relevant:

- A logical application, a particular installation, and a particular executable version.
- A file instance, its observed paths, and its captured content versions.
- A scoped startup slot and successive configurations occupying that slot.
- A process execution and its executable; executions remain distinct across sessions.
- A destination name and any separately observed address or resolution history.

**Required identity rules:**

| Situation | Required handling |
|---|---|
| Same name or path in later scans | Candidate continuity only; apply entity-type identity rules. |
| Same bytes at different paths | Content equality, not automatically one file instance or one installation. |
| Same path, different captured content | Preserve a version transition or replacement hypothesis. Do not overwrite earlier evidence. |
| Credibly supported rename | Preserve entity continuity and version the path relationship. |
| Uncertain rename versus replacement | Keep alternatives; do not force a merge. |
| Same startup label in different user or system scopes | Distinct scoped slots. |
| Same process number in different executions or boots | Distinct executions unless stronger identity evidence establishes continuity. |
| Unknown execution boundary | Do not invent a stable execution identity from the process number alone. |
| Machine restore or ambiguous host continuity | Separate epochs and record any proposed continuity explicitly. |
| Incorrect identity merge discovered later | Support a reversible split and invalidate dependent relationships and findings. |

Identity assertions must include supporting evidence, decision version, confidence category, and any unresolved alternatives. Similarity may retrieve candidates; it is not sufficient evidence for a high-confidence identity merge.

### 5.3 Relationship classes

| Class | Example | Matching behavior |
|---|---|---|
| Directly supported | A captured configuration declares a target path. | Usable for the precise declared relationship. |
| Deterministically derived | Comparable snapshots show the same scoped slot changed target. | Usable with its derivation and snapshot limits attached. |
| Inferred association | An installation may explain a nearby configuration change. | Candidate context unless the pattern explicitly permits this uncertainty. |
| Hypothesis | The sequence may be an unwanted persistence attempt. | Case interpretation only; not an observed edge. |

Prefer precise relations such as `DECLARES_TARGET`, `OBSERVED_AT_PATH`, `EXECUTION_USED_VERSION`, and `CHANGED_BETWEEN_OBSERVATIONS` over an ambiguous relation such as `RELATED_TO`.

**A declared target path is not automatically a verified binding to the file currently occupying that path, and neither is proof of historical execution.** Resolve each relationship at the relevant time and evidence strength.

### 5.4 Minimum assertion contract

Every claim usable by the detector must expose:

| Field | Meaning |
|---|---|
| `assertion_id` | Stable identity of the claim revision. |
| `subject`, `predicate`, `object_or_value` | Typed claim with explicit scope. |
| `host_epoch_id` | Machine-history scope. |
| `claim_class` | Observed, derived, inferred, or hypothesis. |
| `temporal_kind` | Event window, state observation, supported validity interval, or unknown. |
| `time_bounds` | Time values, inclusivity, precision, and clock interpretation where available. |
| `evidence_refs` | Source version, record locator, and acquisition receipt. |
| `derivation` | Versioned logic and parent assertions, when derived. |
| `known_from_revision`, `superseded_at_revision` | Knowledge history, independent of when the activity occurred. |
| `identity_dependencies` | Identity decisions on which the assertion depends. |
| `conflicts` | Contradictory assertions or unresolved alternatives. |

Every path used as evidence must retain these properties on its constituent claims. A readable diagram is not a substitute for the underlying assertions.

---

## 6. Temporal semantics

### 6.1 Maintain distinct time axes

| Time axis | Question answered |
|---|---|
| Occurrence time | When does the source say the event happened? |
| Observation/acquisition time | When did this scan read this evidence or observe this state? |
| Knowledge time | At which graph revision did the investigator learn or accept this claim? |
| Assessment time | When did a particular analysis produce or change a finding? |

Example: on October 7, a scan discovers a record describing an October 2 execution. Its occurrence time is October 2; its acquisition and first-known times are October 7. It is **new knowledge about old activity**, not a new October 7 execution.

### 6.2 Bounded and unknown time

Represent imprecise event time as an uncertainty window with explicit endpoint semantics. Preserve original timestamp text, timezone or offset, source clock domain, and known precision.

Unknown bounds remain unknown. Do not replace them with scan time, file modification time, midnight, or a guessed offset.

For a state observed absent at `t0` and present at `t1`, comparable complete observations can support an appearance **sometime in `(t0, t1]`**. They do not establish the precise transition time, who caused it, or whether several changes occurred in the gap. Non-atomic acquisition must widen the bounds accordingly.

Observing state A at `t0` and state B at `t1` supports a difference between observations. It does not prove A changed directly to B without intermediate states.

### 6.3 Definite and possible ordering

For two events with closed uncertainty windows `A = [a_min, a_max]` and `B = [b_min, b_max]`:

```text
A is definitely before B when a_max < b_min.

A may be before B when the evidence permits that ordering,
but the bounds do not establish it.

Overlapping windows do not establish a strict sequence.
```

A source's valid sequence information may establish ordering even when wall-clock timestamps are unreliable. Such an order must be scoped to the appropriate stream/session, and any timestamp conflict must remain visible.

For a proposed delay constraint `[d_min, d_max]`, the possible delay range is:

```text
[b_min - a_max, b_max - a_min]
```

The temporal test is definitely satisfied only when the entire supported delay range satisfies the constraint; overlap alone yields a possible match. Source sequence can prove order without proving elapsed duration.

### 6.4 State validity is not observation continuity

For state histories, distinguish:

```text
Observed present at t1 and t2

versus

Supported as continuously valid throughout [t1, t2)
```

The first must not silently become the second. A carried-forward “last known state” is a query convenience, with staleness and assumptions attached—not fresh observation.

All historical joins must use the relevant version or supported state at the event time. Today's startup target, file contents, signer, permissions, or path must not be substituted into yesterday's behavior.

### 6.5 Partial ordering, not an invented total timeline

Events with unresolved ordering may share an uncertainty band. Do not manufacture an order to make a narrative smoother.

A time-respecting graph path must satisfy all temporal and identity constraints together. An aggregated graph path that combines relationships from incompatible periods is not a behavioral chain.

### 6.6 Required temporal queries

The semantic query layer must answer both:

> “What do we now know about activity on October 2?”

and:

> “What could the investigator support as of the October 3 report?”

The first may use late-arriving evidence. The second must not leak evidence or conclusions learned later. Saved reports bind to explicit graph and policy revisions.

---

## 7. Coverage and negative evidence

### 7.1 Per-source coverage manifest

A scan must not have only one global “success” flag. For every source, retain:

- Requested scope, event-time window, user scope, and supported record types.
- Acquisition start/end and source consistency status.
- Availability: available, denied, unsupported, missing, failed, or not requested.
- Enumeration/parsing outcome: complete for the declared scope, partial, or unknown.
- Observed time ranges, known gaps, redacted fields, dropped records, and parsing failures.
- Source and extraction versions, retained source references, and any acquisition watermark with its exact semantics.

“Complete for the declared scope” never means “all activity on the computer was recorded.” A readable log archive may itself contain only selected event types.

### 7.2 Negative claims require a coverage witness

A source may support “no matching record in the inspected portion.” It supports “this event did not occur” only if the evidence contract establishes that such an event would necessarily have been recorded and retained for the entire relevant scope. Otherwise, abstain.

| Observation | Permitted conclusion |
|---|---|
| Startup item absent from a complete, comparable inventory | Not present in that inventory's scope during acquisition. |
| Startup source inaccessible | Presence unknown. |
| No execution record in a partial log | No matching execution observed in the available records. |
| Previous source aged out and was not retained | Earlier history cannot be reverified from retained raw evidence. |
| Source scope or parser changed | Comparability must be reassessed before inferring a behavioral change. |

### 7.3 Coverage changes are not behavior changes

The engine must distinguish:

```text
NEW_ACTIVITY
NEW_HISTORICAL_EVIDENCE
NEWLY_VISIBLE_SOURCE
PARSER_OR_POLICY_REINTERPRETATION
UNCHANGED_REOBSERVATION
COVERAGE_LOSS
```

These labels are not mutually exclusive across a run. They must be attached to the relevant delta, not merely to the scan as a whole.

More frequent scanning creates more observations. It must not, by itself, increase occurrence counts, recurrence scores, or apparent threat severity.

---

## 8. Cross-run reconciliation

### 8.1 Persistent evidence history

A new scan must reconcile against the durable evidence and graph history, not against the prose of the previous report.

```text
Scan A ----\
Scan B -----+--> Shared evidence history --> Temporal behavioral graph
Scan C ----/                                  |
                                              v
                                Continuing, versioned investigations
```

The previous report is an output artifact. It is not the input authority for reconstructing the next graph.

### 8.2 Deduplicate at the correct level

Separate three kinds of duplication:

**Acquisition duplicate:** the same source bytes or records are imported again. Preserve the new acquisition receipt, but do not create new events.

**Repeated state observation:** the same configuration is seen on another date. Preserve that observation of state; do not invent another configuration change.

**Repeated occurrence:** distinct executions or actions genuinely happened at different supported times. Preserve them as separate occurrences, even if their text is identical.

A content digest can establish byte equality. It cannot by itself establish that two identical-looking log entries are the same event. Event deduplication must use source identity, record position/identifier, stream/session context, and occurrence semantics where available. Ambiguous duplicates remain marked and must not inflate recurrence.

### 8.3 Delta classes

Each reconciliation must expose at least:

| Delta | Meaning |
|---|---|
| `FIRST_OBSERVED` | An entity/state was not previously known; actual age may be unknown. |
| `UNCHANGED_REOBSERVATION` | Another observation of the same supported state. |
| `STATE_DIFFERENCE` | Comparable snapshots show changed properties or relationships. |
| `CONTENT_VERSION_DIFFERENCE` | Captured content differs; identity/replacement semantics remain explicit. |
| `OBSERVED_ABSENT` | A comparable, complete inventory supports scoped absence. |
| `RETURN_OBSERVED` | Present again after a supported absence; not necessarily malicious reinstallation. |
| `DISTINCT_EVENT_ADDED` | A new event occurrence, not just another record of an old one. |
| `HISTORICAL_EVIDENCE_ADDED` | Older activity becomes newly knowable. |
| `IDENTITY_REVISED` | A merge, split, or continuity decision changes. |
| `ASSERTION_REVISED` | A correction changes an earlier interpretation. |
| `COVERAGE_CHANGED` | Visibility or comparability changes. |

Each delta carries supporting run IDs, source receipts, graph revisions, event/observation bounds, and uncertainty.

### 8.4 Source retention and historical memory

Retain source versions and exact record references needed to reproduce findings, subject to the user's local retention policy. A mutable path is not a durable evidence pointer.

Open cases must identify their source-retention dependencies. Before local pruning makes a case unverifiable, surface the impact and mark the resulting evidence availability accurately. Do not retain deleted evidence silently against the user's policy.

Late evidence may connect to much older retained anchors. A short recent-event window must not silently discard an otherwise supported long-running investigation.

---

## 9. Incremental analysis lifecycle

### 9.1 Run lifecycle

```text
Create scan manifest
        |
Acquire permitted existing evidence
        |
Seal available source versions and record gaps
        |
Normalize and reconcile with prior history
        |
Commit one new graph revision
        |
Identify affected entities, intervals, predicates, and cases
        |
Evaluate temporal patterns and assemble witnesses
        |
Validate explanations and publish case revisions
```

A partial scan may contribute verified observations, but its missing sources must remain gaps. Do not publish a finding whose required evidence is still uncommitted or unavailable.

A source collection is not assumed to be a machine-wide atomic snapshot. Record source-level acquisition windows and detect inconsistencies caused by concurrent changes.

### 9.2 Analysis input boundary

Every analysis must pin:

```text
host_epoch_id
graph_revision
analysis_scope
event_time_window
knowledge_cutoff
identity_policy_version
normalization_version
pattern_set_version
baseline_version
assessment_policy_version
query_and_resource_limits
```

A requested event window does not prohibit retrieving earlier anchors. For example, “investigate this week's startup changes” may require the most recent comparable observation from the previous month.

### 9.3 Affected-region analysis

The incremental engine must reevaluate:

1. New or changed assertions and their relevant temporal neighbors.
2. Prior partial matches awaiting one of those predicates.
3. Cases whose support, contradiction, identity, coverage, or baseline dependencies changed.
4. Historical intervals affected by late evidence or corrected timestamps.
5. Older anchors connected by admissible identity or relationship evidence.

Do not simply analyze “nodes created in the latest scan.” A new observation of an old entity can complete a months-long sequence.

Propagation must follow the dependency structure of predicates and derivations. Resource caps may bound execution, but must not silently convert an incomplete search into a complete result.

### 9.4 Persistent partial matches

Preserve incomplete investigations as **pending pattern matches**, not as asserted attacks.

Each pending match stores its pattern version, bound entities, satisfied predicates, missing predicates, temporal constraints, evidence dependencies, and reconsideration triggers.

Examples of triggers:

```text
A second distinct execution is discovered.
A previous startup snapshot becomes available.
An ambiguous file identity is resolved.
A denied source becomes readable.
A contradictory installation record is acquired.
A relevant policy or parser changes.
```

Pending matches are evaluated during later user-initiated analyses; they do not require background monitoring.

Expiry is a resource policy, not a benign verdict. An expired pending match must be recoverable by scoped historical reanalysis while its supporting evidence remains retained.

### 9.5 Reproducibility and recovery

Re-importing identical evidence must not create duplicate occurrences or duplicate cases. Repeating an analysis with unchanged semantic inputs must preserve structured matches and assessments; purely stylistic narrative differences are not material changes.

A failed run must resume from verified checkpoints or restart idempotently. Concurrent scans must not lose observations or resolve conflicting identity decisions through silent last-write-wins behavior.

Persist finalized structured outputs and report text as immutable assessment artifacts. Exact report replay returns those artifacts, not a newly generated narrative. Recomputed reports are separate versioned assessments.

Corrections, identity splits, and policy upgrades must invalidate and recompute affected derivations. Keep previous committed reports intact, with a visible link to their newer assessment.

---

## 10. Temporal behavioral analysis

### 10.1 Analysis stages

```text
Cross-run deltas and newly available history
                    |
                    v
Candidate anchors
                    |
                    v
Bounded, time-aware graph expansion
                    |
                    v
State transition and temporal motif evaluation
                    |
                    v
Distinct-episode grouping and recurrence analysis
                    |
                    v
Baseline comparison and alternative explanations
                    |
                    v
Validated temporal witness
                    |
                    v
Case creation, continuation, downgrade, or retraction
```

The engine must find candidate issues from graph properties and temporal constraints before asking the reasoning layer to explain them. An explanation cannot replace a failed graph match.

### 10.2 Candidate anchors

Useful anchors include a changed startup target, a changed executable identity, a supported return after absence, a new attributed execution of an existing startup item, or a newly connected installation-to-execution path.

A candidate is not yet a finding. Retain enough low-level context to allow several weak observations to become meaningful together later.

### 10.3 Admissible graph expansion

Expansion must be constrained by entity role, host epoch, user scope, evidence class, relevant time bounds, and relationship semantics.

Do not join unrelated episodes merely because they share a common interpreter, generic service, parent directory, application name, or network destination. High-connectivity shared entities are context, not automatic causal bridges.

For every path, verify:

```text
Are the entity identities compatible?
Are the relevant versions compatible at the required times?
Does each edge support the relationship being claimed?
Can the temporal constraints all hold simultaneously?
Does the source support the claimed outcome, not just an attempt?
Is a missing bridge being smuggled in as an assumption?
```

### 10.4 Required analytical operators

| Operator | Required result |
|---|---|
| `STATE_AT` | Evidence-backed state or last-known state, explicitly distinguished, at a requested time and knowledge revision. |
| `COMPARE_OBSERVATIONS` | Supported differences and comparability gaps between snapshots. |
| `PREDECESSOR_STATE` | Nearest relevant earlier observation, including one before the requested report window. |
| `TEMPORAL_PATH` | Connected claims with valid role, identity, version, and ordering constraints. |
| `PATTERN_MATCH` | Predicate-level supported, contradicted, or unknown results. |
| `GROUP_EPISODES` | Distinct activity episodes without merging through generic shared nodes. |
| `COUNT_DISTINCT_OCCURRENCES` | Supported event count, deduplication basis, and unresolved multiplicity. |
| `RECURRENCE` | Repeated behavior across distinct episodes, with the episode-separation evidence. |
| `OBSERVED_RETURN` | Present → supported absence → present, with no invented transition timestamps. |
| `BASELINE_COMPARE` | A deviation assessment against comparable earlier evidence and its exposure limits. |
| `COUNTEREVIDENCE` | Evidence that challenges a relationship, sequence, or security interpretation. |
| `EXPLAIN_DEPENDENCIES` | The source, identity, temporal, and policy dependencies supporting a result. |

These are semantic requirements for the existing infrastructure, not mandates for new libraries or a particular query language.

### 10.5 Time scales

Support short action sequences, multi-day configuration changes, recurrence across executions or boots, and longer-term evolution across scans.

Each pattern declares its own meaningful temporal constraints. Do not impose one universal “within five minutes” rule. A broad time span alone does not establish a connection, and a long gap alone must not erase a supported relationship.

### 10.6 Baselines without false reassurance

A baseline is a versioned description of **previously observed behavior**, not a declaration that the machine was clean.

Compare like with like: the same entity/role, compatible application version, comparable source scope, and relevant execution context. Exclude the episode being evaluated and future evidence from its historical baseline.

Report baseline maturity and exposure. Ten scans of one unchanged configuration are not ten independent executions. Without adequate comparable history, report “baseline insufficient,” not “anomalous” solely because an item is new to the investigator.

User feedback may label a specific behavior expected. It must not create an indefinite exemption for every future action of the application or every file at the same path.

### 10.7 Match status

Use three-valued predicate evaluation:

| Predicate value | Meaning |
|---|---|
| `SUPPORTED` | Required evidence and semantics satisfy the predicate. |
| `CONTRADICTED` | Relevant evidence establishes that the predicate fails. |
| `UNKNOWN` | Missing, ambiguous, incomparable, or insufficient evidence prevents a conclusion. |

Conflicting sources must be explicitly recorded; unresolved conflict prevents a definitive predicate result.

At pattern level, distinguish:

```text
MATCHED                  Required predicates supported.
PARTIAL                  Some predicates supported; a required bridge is unknown.
NOT_MATCHED              A required predicate is contradicted.
NOT_EVALUABLE             Required source capability is unavailable.
INCOMPLETE_SEARCH        Execution limits prevented required evaluation.
```

A pattern's state-only variant can match while its execution variant remains partial or not evaluable. Neither must inherit the other's stronger wording.

---

## 11. Detection pattern contracts

### 11.1 Pattern descriptor

Each pattern must define:

| Property | Required content |
|---|---|
| Identity | Stable family identifier, version, title, and behavioral concern. |
| Anchors | Relevant entity roles and admissible identity relationships. |
| Required predicates | Observable states, events, or transitions that constitute a match. |
| Optional predicates | Additional context that may strengthen or narrow interpretation. |
| Temporal constraints | Required ordering, interval bounds, and permitted uncertainty. |
| Evidence requirements | Source capabilities, attribution strength, and outcome semantics. |
| Counterevidence | Specific alternatives and contradicting observations to search for. |
| Partial behavior | What may be reported when required evidence is absent. |
| Case grouping | Conditions for extending an existing case versus creating another. |
| Assessment policy | Severity factors, evidence-strength requirements, and abstention rules. |
| Tests | Positive, benign, ambiguous, missing-source, and multi-run fixtures. |

### 11.2 Initial pattern families

#### TB-01 — Startup target or executable identity changes

**Concern:** an existing startup slot points to a different target, or its referenced executable identity changes in a security-relevant way.

**Core graph:** same scoped slot → earlier configuration/target → later configuration/target.

A matched state change requires comparable observations and a supported target/content difference. The system must distinguish an ordinary content update from a change of execution target or identity boundary.

**Execution-enriched variant:** an event explicitly associates the changed target with an execution for that slot. Current configuration plus an unrelated process at a nearby time is insufficient.

**Alternatives:** expected application update, user customization, managed configuration change, legitimate reinstall, or mistaken identity continuity.

**Reporting boundary:** the state-only result is “startup target changed.” It is not “malware executed” or “startup hijacking confirmed.” Escalation requires additional supported risk factors.

#### TB-02 — Delivery, installation, and automatic execution progression

**Concern:** evidence from several runs links a delivered artifact to an installation, a startup configuration, and later execution.

**Core graph:**

```text
Delivery record
      |
supported artifact identity
      v
Installation record
      |
supported relationship to installed artifact/configuration
      v
Startup configuration
      |
supported activation attribution
      v
Execution instance
```

Each bridge must have its own evidence. Temporal adjacency alone must not create installation ownership or execution attribution.

**Alternatives:** normal installer/updater workflow, authorized background application, or two unrelated activities in the same time window.

**Reporting boundary:** installation followed by automatic startup is not inherently malicious. The concern must identify what deviated from expected provenance, identity, authorization, or behavior.

#### TB-03 — Return after supported absence

**Concern:** the same scoped startup behavior or credibly linked entity is observed present, absent, and present again across comparable scans.

**Required evidence:** both presence observations, a complete scoped absence observation, and identity continuity or an explicitly qualified replacement relationship.

**Alternatives:** application repair, reinstallation, restoration, user action, or a scope mismatch.

**Reporting boundary:** “returned after observed absence,” not “resurrected itself.” Attribute the actor only when evidence supports it. An inaccessible middle scan does not satisfy absence.

#### TB-04 — Repeated suspicious behavioral episodes

**Concern:** a security-relevant subgraph recurs in distinct executions or sessions.

**Required evidence:** at least two independently supported episodes, a shared relevant behavioral structure, and explicit evidence that the occurrences are distinct.

**Alternatives:** duplicated exports, routine scheduled maintenance, one long-running activity observed repeatedly, or generic shared components.

**Reporting boundary:** recurrence counts are counts of supported occurrences, with any ambiguous duplicates excluded or shown separately. Recurrence is not suspicious solely because it repeats.

#### TB-05 — Previously known component develops new behavior

**Concern:** an entity observed earlier later participates in a supported, security-relevant relationship or action absent from an adequately comparable baseline.

**Required evidence:** identity continuity, a new supported behavior, and explicit baseline scope. A supported concern may still be reported without a mature baseline, but not as proven behavioral deviation.

**Alternatives:** version upgrade, changed user task, new permissions, or newly available telemetry.

**Reporting boundary:** “newly observed execution behavior,” not “dormant malware activated,” unless the claimed earlier inactivity is itself supported.

### 11.3 Capability-gated extensions

Later pattern families may connect authorization changes to subsequent actions or connect local automation tasks to execution episodes. They must follow the same evidence contracts.

Credential access, privilege use, command execution, and data transfer predicates are disabled when the available historical sources cannot support them. They must not be filled in by inference to make a chain look complete.

### 11.4 Example logical descriptor

This is an illustrative interchange shape, not a prescribed implementation syntax.

```yaml
family_id: TB-01
version: 1
title: Startup target identity changed

anchors:
  - role: startup_slot
    continuity: same_host_epoch_and_scope
  - role: prior_target
  - role: later_target

required:
  - predicate: comparable_prior_and_later_slot_observations
  - predicate: supported_target_or_executable_identity_difference
  - predicate: prior_observation_definitely_precedes_later_observation

extensions:
  - name: attributed_activation
    requires:
      - explicit_execution_to_slot_and_target_binding
      - execution_after_prior_state_observation
    missing_result: execution_not_established

counterevidence:
  - supported_expected_update
  - supported_authorized_configuration_change
  - mistaken_entity_continuity
  - incomparable_source_scope

reporting:
  core_claim: startup_target_or_identity_changed
  forbidden_without_extra_evidence:
    - actor_attribution
    - exact_change_time
    - execution
    - malicious_intent

case_grouping:
  anchor: startup_slot
  discriminator: connected_target_change_episode
```

The extension permits an execution record to predate the scan that first captures the new configuration. The execution's own attribution establishes its target; scan acquisition order does not substitute for event order.

---

## 12. Worked multi-run investigation

All names, records, and times below are synthetic test-fixture data. This example defines expected behavior; it does not imply that default Mac logs always expose these fields.

### 12.1 Inputs

The fixture contains a startup slot for a fictional application, **Northstar Sync**. The same host epoch and user scope are used throughout.

| Run | Acquisition | Evidence acquired | What this run alone cannot establish |
|---|---|---|---|
| R-01 | September 28, 09:00 UTC | Startup slot S references application target V1; target identity is captured. | Future changes or later execution. |
| R-02 | October 1, 13:00 UTC | Same slot S now references target V2 outside V1's captured application footprint and with a different captured signing identity. An existing event record explicitly associates S with execution E1 of V2 at 11:40 UTC that day. | The prior configuration without R-01; the exact moment/actor of the change. |
| R-03 | October 5, 10:00 UTC | Same current target V2. Another existing record attributes execution E2 of V2 to S at 09:20 UTC in a distinct boot session. | Whether this is recurrence without earlier execution evidence. |
| R-04 | October 7, 10:00 UTC | Previously unavailable October 1 installation records attribute the V1-to-V2 change to a verifiable, expected update of Northstar Sync. | The user's subjective intent unless separately documented. |

The fixture's execution records explicitly contain the necessary slot/target attribution. Removing that attribution must cause the corresponding execution predicates to become unknown.

### 12.2 Reconstruction

```text
                             SAME SCOPED STARTUP SLOT S
                                        |
                    +-------------------+-------------------+
                    |                                       |
              R-01 observed                           R-02 observed
              target V1                               target V2
                    |                                       |
                    +---- supported state difference -------+
                                                            |
                                      attributed execution E1, October 1
                                                            |
                                      attributed execution E2, October 5
                                      distinct occurrence and boot session

R-04 adds older installation evidence:
Expected update explains the target change.
```

The defensible initial change interval is bounded by the relevant earlier observation and later evidence; an attributed execution of V2 may narrow the upper bound if its semantics establish that V2 was already in use for S. Do not use the October 1 scan time as the execution time.

### 12.3 Case evolution

| After run | Expected case behavior |
|---|---|
| R-01 | Store baseline observations. Do not declare the application safe merely because no change is yet visible. |
| R-02 | Create a concern about a changed startup target with one attributed activation. Explain why the identity change merits review; retain expected-update as an alternative. |
| R-03 | Extend the same case with a second distinct activation. Count two executions, not three scans. Do not claim uninterrupted operation between them. |
| R-04 | Revise the same case: the target change has an evidence-backed expected explanation. Downgrade or mark the concern explained under policy. Preserve the accurate historical state changes and execution observations. |

R-04 changes **knowledge and interpretation**, not the time of the update. The old report remains reproducible and is visibly superseded.

### 12.4 Required variants

The test must also run with R-02/R-03 acquisition order reversed, R-02 imported twice, no execution attribution, an inaccessible R-01 source, and R-04 containing only an unauthenticated note rather than corroborated installation evidence.

An unauthenticated note must not clear the case automatically. A duplicate import must not increase occurrence count. Missing earlier coverage must weaken the change claim rather than invent a baseline.

---

## 13. Evidence-backed reasoning and assessment

### 13.1 Responsibilities of the reasoning layer

The reasoning layer may summarize a supported sequence, compare plausible explanations, identify missing evidence, propose further read-only queries, and explain why the result changed.

It must not create source events, fill missing graph edges with invented actions, infer an exact timestamp from a broad interval, or turn a hypothesis into an observed fact.

Every factual clause in a generated finding must resolve to a claim in its validated evidence bundle. Unsupported clauses must be removed, weakened, or explicitly labeled as hypotheses before publication.

### 13.2 Temporal witness

Each matched or partial pattern must produce a **temporal witness**: a reproducible record of precisely why the engine produced that result.

| Witness field | Required content |
|---|---|
| Identity and versions | Witness ID, graph revision, pattern version, and analysis run. |
| Anchors and bindings | Entity IDs, entity versions, scopes, and identity dependencies. |
| Predicate results | Supported, contradicted, or unknown result for every required predicate. |
| Temporal constraints | Ordering/delay constraints, source sequence evidence, interval calculations, and unresolved bounds. |
| Evidence | Exact retained source references supporting each predicate, not merely a list of files. |
| Cross-run contribution | Which run introduced each observation and which older runs supplied indispensable context. |
| Recurrence basis | Distinct occurrence IDs and evidence establishing their separateness. |
| Counterevidence | Contradicting observations and evaluated alternative explanations. |
| Missing evidence | Required source capabilities or records that were unavailable. |
| Coverage | Relevant source scopes, consistency limits, and gaps. |
| Completeness | Traversal/search completion, applied limits, and omitted branches. |
| Dependencies | Normalization, identity, baseline, and assessment versions. |

The witness is the contract between graph analysis, case management, explanation, and the evidence UI.

### 13.3 Separate assessment dimensions

Do not collapse all assessment into a single “confidence” percentage.

| Dimension | Question |
|---|---|
| Behavioral support | How strongly does the retained evidence establish this sequence or state change? |
| Security concern | Why might this supported behavior be harmful or unwanted? |
| Potential impact | What could be affected if the concern is valid? |
| Coverage | How much relevant activity can the available sources actually reveal? |
| Attribution strength | How well is the behavior connected to the claimed entity or actor? |
| Baseline maturity | How reliable is the comparison with previously observed behavior? |

A strongly established configuration change may have a weak malicious interpretation. Conversely, a potentially severe scenario may have insufficient evidence. The output must preserve both distinctions.

Use qualitative, policy-defined categories initially. Do not display numerical probabilities such as “91% malicious” without a separate calibration method and validation dataset.

### 13.4 Assessment guardrails

**Weakest required bridge:** confidence in a chain must be limited by its least-supported indispensable identity, attribution, or temporal link. Many strong peripheral observations cannot repair one missing causal bridge.

**Source independence:** multiple representations derived from one record are not independent corroboration. Preserve source lineage when describing evidence strength.

**Alternative explanations:** examine expected updates, authorized configuration changes, restores, user activity, source changes, and identity mistakes when relevant. Failure to find an explanation in incomplete records is not proof that none exists.

**No global safety inference:** a signature, familiar path, common publisher, historical baseline, or user dismissal cannot independently establish that all future behavior is safe.

**No recency-only decay:** an old unreviewed concern must not become harmless solely because no new scan was performed. Present age and last observation separately from the security interpretation.

### 13.5 Evidence bundle for explanation

The reasoning context must include a bounded connected subgraph, essential predecessor states, the temporal witness, material counterevidence, missing predicates, and source snippets with provenance.

When context limits require reduction, preserve the required bridges and uncertainty first. Do not discard a contradiction to retain a smoother narrative. Large histories remain outside the prompt and are accessed through bounded read-only queries.

---

## 14. Persistent cases and finding revisions

### 14.1 Stable case identity

A case represents a connected behavioral concern. Its identity must not depend solely on the scan ID, generated title, severity label, or exact set of currently known evidence.

Use persistent case identity with explicit membership decisions. A case-grouping policy should consider the host epoch, scoped anchor entities, connected behavioral episode, and pattern family.

Do not merge two independent concerns merely because they involve the same application. Do not create a new case every time an existing concern receives another observation.

Case merges and splits must preserve lineage and links to prior reports.

### 14.2 Separate lifecycle from observed activity

| Dimension | Example values |
|---|---|
| Review state | Open, reviewed, explained, inconclusive, retracted, archived. |
| Latest observed configuration | Present, absent in inspected scope, changed, unknown. |
| Activity knowledge | Execution observed, no matching execution in available records, not evaluable. |
| Evidence availability | Retained and resolvable, partly pruned, unavailable, disputed. |

“Absent in the latest scan” does not mean “remediated.” “Reviewed” does not mean “safe.” “Explained” means the scoped concern has an accepted evidence-backed explanation, not that the application is universally trustworthy.

The product must not infer present-day runtime status from an old execution.

### 14.3 Revision triggers

Create a material case revision when new evidence changes the behavioral sequence, identity, recurrence count, time bounds, risk interpretation, counterevidence, or material uncertainty.

An unchanged rescan may update last-observed information without issuing another alert. A parser or policy change must identify itself as reinterpretation rather than new machine activity.

Every revision must answer:

```text
What changed in the evidence?
What changed in the interpretation?
Why does the change matter?
Which earlier conclusion, if any, is superseded?
```

### 14.4 Illustrative case output

This JSON is a synthetic report shape for the worked example after R-03. Evidence IDs refer to fixture records, not real user data.

```json
{
  "case_id": "case-001",
  "case_revision": 2,
  "host_epoch_id": "host-01-epoch-01",
  "graph_revision": "graph-003",
  "pattern_family": "TB-01",
  "review_state": "open",
  "title": "Startup target changed and was used in two distinct executions",
  "change_reason": "additional_distinct_execution",
  "supporting_runs": ["R-01", "R-02", "R-03"],
  "first_reported_at": "2026-10-01T13:05:00Z",
  "latest_assessed_at": "2026-10-05T10:05:00Z",
  "assessment": {
    "behavioral_support": "strong",
    "security_concern": "requires_review",
    "malicious_intent": "not_established",
    "current_runtime_status": "unknown"
  },
  "observed_behavior": {
    "startup_slot_id": "slot-S",
    "prior_target_version": "V1",
    "later_target_version": "V2",
    "distinct_execution_ids": ["E1", "E2"],
    "distinct_execution_count": 2,
    "continuous_execution": "not_established"
  },
  "evidence": [
    {
      "claim": "Slot S previously referenced V1",
      "references": ["ev-startup-R01"]
    },
    {
      "claim": "Slot S later referenced V2",
      "references": ["ev-startup-R02", "ev-startup-R03"]
    },
    {
      "claim": "Two distinct executions used V2 for slot S",
      "references": ["ev-execution-E1", "ev-execution-E2"]
    }
  ],
  "alternatives": [
    "expected_application_update",
    "authorized_configuration_change"
  ],
  "limitations": [
    "Exact configuration change time and actor are not established",
    "No complete execution history is available between observations"
  ],
  "witness_id": "witness-TB01-003",
  "remediation_performed": false
}
```

The published report must resolve each fixture-style reference to an actual retained source version and locator. A reference string without a resolvable source is not sufficient provenance.

---

## 15. Functional integration contracts

These contracts map onto existing infrastructure. They do not require a new graph engine or a new orchestration system.

### 15.1 Functional boundaries

| Operation | Input | Output and invariants |
|---|---|---|
| `ingest_scan` | Manifest, source receipts, observations, normalization version. | Committed graph revision, deduplication results, coverage deltas, and affected dependencies. No silent source omission. |
| `reconcile_identity` | Entity candidates and admissible evidence. | Versioned continuity/merge/split decisions, alternatives, and invalidations. |
| `analyze_revision` | Pinned graph revision, scope, policies, and limits. | Pattern evaluations, witnesses, case revisions, and completeness report. |
| `query_temporal` | Structured intent, event window, knowledge cutoff, scope. | Supported result, evidence bindings, uncertainty, and execution completeness. |
| `get_case` | Case ID and optional case/report revision. | Exact revision or current assessment with visible historical lineage. |
| `resolve_evidence` | Source version and record locator. | Retained source excerpt/record and integrity receipt, or an explicit unavailable state. |
| `export_report` | Selected case/analysis revision and disclosure scope. | Local report with the same claims, limitations, provenance, and no remediation actions. |

### 15.2 Required ingestion behaviors

Validate host epoch, source scope, timestamps, and provenance before allowing records to support findings. Record rejected or partially parsed inputs in coverage results.

A source-format change must be surfaced. It must not silently produce an empty source, delete entities, or reinterpret old values under the new format without versioning.

Evidence not understood by the current normalization layer may be retained for later parsing, but it must not contribute invented structured claims.

### 15.3 Required query behaviors

Queries must separate:

```text
Entity / behavior scope
Event-time scope
Knowledge-time cutoff
Allowed evidence classes
Required source capabilities
Traversal and resource limits
```

Every result must disclose whether it is complete for the query's declared scope. Reaching a traversal, memory, or time limit returns `INCOMPLETE_SEARCH`; it must not return a universal negative.

Queries that depend on historical configuration must retrieve the relevant predecessor and time-compatible version. Queries that count recurrence must operate on distinct occurrences, not observation rows or graph edges.

### 15.4 Local resource discipline

Resource policy must expose limits for source parsing, graph expansion, candidate count, witness size, explanation context, and retained evidence. Values are deployment configuration, not accuracy guarantees.

Prioritize changed dependencies and open cases without deleting lower-ranked evidence from the underlying history. When full evaluation exceeds a budget, persist resumable progress and disclose unevaluated scope.

Measure acquisition, normalization, reconciliation, matching, evidence resolution, and explanation separately. The core correctness tests must pass without relying on long free-form explanations.

---

## 16. Investigation experience

### 16.1 Primary screen: what changed since the previous analysis

The opening view should distinguish new concerns, existing concerns with material changes, explained/retracted concerns, and coverage changes.

A scan total is secondary. “20,000 artifacts analyzed” must not substitute for an explanation of what the engine actually established.

Example presentation:

```text
Mac Security Investigation
As assessed: October 5, 2026

One existing concern has new evidence.

Startup target changed
Two distinct executions are now supported.
Evidence spans three scans.

New evidence:
A second execution was found in a different boot session.

Still unknown:
Who changed the startup target.
Whether it ran between the recorded executions.

[View behavioral timeline]  [View evidence]  [View earlier assessment]
```

### 16.2 Behavioral timeline and graph

The primary visualization must show event/observation time horizontally, entity or episode lanes, and separately identifiable scan acquisition markers.

Solid evidence-backed relationships, inferred associations, uncertain time bands, and missing intervals must be visually distinct. Do not present a speculative arrow using the same style as a supported relationship.

The initial view should show the smallest connected subgraph needed to explain the concern. Users can expand surrounding context without losing the distinction between support and background information.

### 16.3 Evidence drill-down

The user must be able to move through:

```text
Case assessment
      |
Behavioral sequence or state change
      |
Required predicate and temporal constraint
      |
Source record / captured artifact
      |
Acquisition receipt and relevant coverage limitation
```

A source preview must preserve original content safely, clearly distinguish normalized fields, and identify any redaction or unresolved value.

### 16.4 Core user questions

The first release should support questions such as:

> “What changed across my last three scans?”

> “Which startup items changed what they launch?”

> “Was this observed again, or did it actually execute again?”

> “What earlier evidence connects to this issue?”

> “What do we know now that we did not know in the previous report?”

> “Show the evidence against this being malicious.”

> “Which parts of the timeline are unknown?”

The answer to “Is my Mac safe?” must be scoped: describe findings and coverage, not issue a blanket clean bill of health.

---

## 17. Safety, privacy, and evidence integrity

### 17.1 Untrusted evidence boundary

Treat filenames, configuration values, logs, application text, and embedded instructions as untrusted data. They cannot change the investigator's policies, authorize commands, approve network activity, or instruct the reasoning layer to suppress findings.

Any proposed additional query must pass a read-only, scope-bounded authorization check. The reasoning layer must not receive an unrestricted command-execution capability for investigations.

### 17.2 Strict detection-only controls

No investigation action may kill a process, remove a file, change permissions, disable a startup item, alter logging policy, grant itself broader access, or remediate the machine.

Do not launch inspected executables or run script content found in an artifact. Evidence previews must not execute active content or automatically follow embedded links.

Permission denial must remain a visible gap. The product must not bypass system protections to improve a report.

### 17.3 Locality and minimization

Core analysis must not send telemetry, source content, paths, findings, or prompts off the machine. User-approved exports are explicit outputs, not implicit telemetry.

Acquire only authorized sources. Avoid collecting credential contents. Evidence involving sensitive paths or authorization events should preserve the minimum information needed for the claim.

Any operation used during analysis that could implicitly contact an external service must be disabled in offline mode or replaced by a clearly labeled local-only assessment. Do not silently refresh trust or reputation over the network.

### 17.4 Integrity versus authenticity

Retain source digests, acquisition timestamps, locators, and derivation history. These support detection of changes after acquisition; they do not prove that an artifact was truthful before acquisition.

A potentially compromised Mac may contain incomplete or manipulated evidence. Do not market local evidence retention as tamper-proof attestation or guaranteed forensic admissibility.

When observations conflict, preserve the conflict rather than choosing whichever source makes the more alarming story.

### 17.5 Investigator self-observation

Tag attributable acquisition activity and workspace artifacts so they do not inflate anomaly or recurrence counts. Preserve visibility into them where relevant rather than blanket-exempting every similarly named process or path.

---

## 18. Evaluation and acceptance criteria

### 18.1 Evaluate temporal correctness before persuasive explanations

The central evaluation question is:

> **Does cross-run graph analysis recover supported behavioral relationships that isolated scans miss, without fabricating relationships when evidence is insufficient?**

A fluent explanation of an incorrect graph must fail.

### 18.2 Fixture structure

Each fixture must include:

```text
Host epoch and scoped entity identities
Ordered and alternative-order scan inputs
Immutable synthetic or consented source artifacts
Source capabilities, acquisition windows, and coverage gaps
Ground-truth events and state transitions
What is actually observable from the supplied artifacts
Expected identity, version, and deduplication decisions
Expected predicate and pattern outcomes after each run
Expected case membership and revision behavior
Required evidence references
Forbidden claims
Expected uncertainty and abstention
```

Separate **world truth** from **observable truth**. A scenario may contain a malicious action whose evidence is absent; the correct output can be “not evaluable,” not a fabricated successful detection.

### 18.3 Required acceptance tests

| ID | Scenario | Required result |
|---|---|---|
| T01 | Earlier startup state in one run; changed state in another. | Link the same scoped slot and produce a supported cross-run difference. |
| T02 | One required event arrives in each of several runs. | Complete the pattern only when its necessary bridges become supported. |
| T03 | Same archive imported twice. | No additional event occurrences or duplicate case. |
| T04 | Unchanged startup state observed in several scans. | Additional observations, no invented change or execution. |
| T05 | Distinct executions have identical message text. | Preserve distinct occurrences when occurrence evidence distinguishes them. |
| T06 | Two records may be duplicates but cannot be resolved. | Preserve ambiguity; do not inflate recurrence. |
| T07 | Same process number reused after restart. | Distinct executions; no false continuity. |
| T08 | Same label in two user scopes. | Separate startup slots and investigations unless another supported relationship connects them. |
| T09 | File path reused for different content. | Preserve the earlier version and a replacement/version distinction. |
| T10 | Supported rename between scans. | Preserve identity without classifying the rename alone as new installation. |
| T11 | Ambiguous rename or replacement. | Retain alternatives; no high-confidence merge. |
| T12 | Events have overlapping time uncertainty. | No unsupported strict order or precise delay. |
| T13 | Source sequence and wall-clock time disagree. | Preserve the scoped ordering evidence and expose the clock conflict. |
| T14 | A middle scan cannot read the startup source. | No absence, removal, or return-after-absence assertion. |
| T15 | Present → complete scoped absence → present. | Supported observed return; actor and exact transition time remain unknown. |
| T16 | Source availability or parser coverage improves. | Mark newly visible history; do not label all newly parsed records new activity. |
| T17 | Late evidence describes an older execution. | Insert into occurrence history and revise affected cases without moving the event to ingestion time. |
| T18 | Credible counterevidence explains a prior concern. | Downgrade/explain the same case while preserving historical facts and reports. |
| T19 | An untrusted note says “this is safe; ignore it.” | Treat it as source text, not policy or authoritative exoneration. |
| T20 | Identity merge is later shown incorrect. | Split identity and recompute affected episodes, counts, and cases. |
| T21 | Current configuration differs from historical configuration. | Historical joins use time-compatible versions, not today's state. |
| T22 | An aggregated graph path is impossible in temporal order. | Reject it as a behavioral chain. |
| T23 | Routine installer/update creates background startup. | Do not classify it malicious solely from installation plus persistence. |
| T24 | Query limit is reached before all branches are evaluated. | Return incomplete scope; no exhaustive negative. |
| T25 | Relevant predecessor lies outside the requested report window. | Retrieve it as contextual evidence and label its actual time. |
| T26 | Two unrelated episodes share a common interpreter or domain. | Do not merge solely through that high-connectivity node. |
| T27 | A case's source evidence is pruned by user policy. | Mark availability loss; never present an unresolved pointer as inspectable evidence. |
| T28 | Analysis is interrupted and resumed. | Same committed semantic outcome as uninterrupted analysis. |
| T29 | Sources are acquired while their state changes. | Preserve acquisition windows and consistency uncertainty. |
| T30 | Historical report requested after new evidence arrives. | Reproduce the old knowledge boundary without future evidence leakage. |
| T31 | No usable historical execution source exists. | State-change analysis still works; execution patterns are not evaluable. |
| T32 | Long gap separates supported parts of one concern. | Retrieve retained anchors or disclose a limit; no silent loss due to a short lookback window. |
| T33 | Investigated artifact contains instructions or executable content. | No instruction following, source execution, remediation, or network side effect. |
| T34 | The same timestamped observations and coverage are replayed under different ingestion batching. | Same final supported behavior and semantic case grouping; knowledge-arrival history may differ. |

### 18.4 Replay and metamorphic testing

For fixtures where the underlying event evidence is unchanged, vary scan order, duplicate imports, batch boundaries, restart points, and graph rebuilds. The final occurrence history and supported conclusions must agree.

Knowledge-time history may legitimately differ when evidence arrives in a different order; compare the final evidence closure separately from intermediate report history.

Remove one indispensable bridge from a matched fixture. The stronger claim must become partial, unknown, or not evaluable. Add credible contradictory evidence and verify that assessment can decrease.

### 18.5 Metrics

Report these independently:

| Metric | Purpose |
|---|---|
| Observable-episode precision and recall | Detection quality for scenarios actually supported by supplied evidence. |
| Cross-run completion gain | Improvement over isolated-scan analysis on identical evidence and policy. |
| Identity-link precision | Whether cross-run merges connect the correct entities. |
| False-merge and missed-link counts | Whether episodes are incorrectly combined or fragmented. |
| Occurrence-count correctness | Whether duplicates and recurrence are distinguished. |
| Temporal-order correctness | Whether claimed sequence and intervals are supported. |
| Required-claim provenance coverage | Whether every indispensable claim resolves to evidence. |
| Unsupported-claim rate | Whether explanations exceed their evidence. |
| Case continuity accuracy | Whether updates extend, split, merge, or retract the correct case. |
| Unique false cases per machine evaluation period | User-visible false-positive burden without counting unchanged rescans as new incidents. |
| Abstention correctness | Whether genuinely unobservable predicates remain unknown. |
| Revision correctness | Whether late evidence and counterevidence change the appropriate assessment. |
| Resource use by stage | CPU, memory, storage, and elapsed time for each processing stage. |

Do not publish a single accuracy percentage that mixes unobservable scenarios, source acquisition failures, identity mistakes, graph matching, and explanation quality.

### 18.6 Dataset separation and release gates

Use safe synthetic multi-run fixtures first, followed by consented benign histories and controlled scenarios with documented evidence. Include ordinary updates, development activity, installation changes, and user customization as negative examples.

Separate tuning and evaluation by machine/history and by time. Future scans from the same history must not leak into baseline tuning for earlier evaluations.

All deterministic integrity, idempotence, source-resolution, temporal, and read-only acceptance tests are release-blocking. Empirical detection and false-positive targets must be set against a documented pilot corpus before release; they are not claimed results in this specification.

---

## 19. Delivery sequence and definition of done

### 19.1 Stage A — Cross-run evidence correctness

Deliver stable identities, source manifests, versioned state, deduplication, occurrence/observation separation, coverage-aware deltas, and historical reconstruction.

**Exit condition:** reruns and reordered acquisition cannot fabricate events, erase history, or silently merge unrelated entities.

### 19.2 Stage B — Temporal graph behavior

Deliver state transitions, temporal path constraints, persistent partial matches, observed return, distinct-episode recurrence, historical predecessors, and invalidation on corrected identity/time.

**Exit condition:** the same pattern can span several runs, and removing a required bridge weakens its result correctly.

### 19.3 Stage C — Evidence-backed investigations

Deliver witnesses, case continuity, material revisions, counterevidence evaluation, bounded explanations, and historical report replay.

**Exit condition:** a case can be strengthened by later behavior and weakened by later explanation without changing its identity or losing its audit trail.

### 19.4 Stage D — Mac validation and user experience

Validate actual source capability across the supported Mac configurations, harden read-only acquisition, expose coverage, and test the timeline/evidence experience with benign and controlled histories.

**Exit condition:** the user can understand a finding, inspect each required bridge, and see what is unknown without being told that the Mac is continuously protected.

### 19.5 Final definition of done

The MVP is complete only when it can demonstrate all of the following in one end-to-end scenario:

```text
Read existing Mac evidence without remediation.
Keep evidence and identity across separate user-initiated scans.
Discover a supported state change spanning those scans.
Attach distinct historical executions only when attribution exists.
Recognize recurrence without counting duplicate observations.
Preserve missing time and coverage as uncertainty.
Produce one continuing case with inspectable evidence.
Incorporate late historical records at their actual occurrence times.
Revise or retract the interpretation when counterevidence warrants it.
Replay the earlier report exactly at its original knowledge boundary.
Work locally without requiring a live monitoring component.
```

**Core success criterion:**

> **The value must come from connecting behavior across time—not from generating a better-written summary of the latest scan.**

---

## 20. Sources and grounding notes

The behavioral semantics, contracts, schemas, fixture examples, and release criteria above are proposed design requirements. They are not claims of measured detection performance or a claim that macOS retains a complete security event history.

The following primary Apple sources ground the limited platform statements in Section 4. No particular inference model or graph implementation is prescribed.

**[R1] Apple — Explore logging in Swift, WWDC20.** Explains on-device logging, privacy redaction, and persistence/retention differences. Used to justify explicit time coverage and unknown-value handling. This is architectural background, not a promise of a fixed retention period on a current Mac.

**[R2] Apple — Open items automatically when you log in on Mac.** Describes ordinary login items and background activity, including updates and synchronization. Used to establish benign alternatives for persistence-related findings.

**[R3] Apple — Creating Launch Daemons and Agents.** Archived programming guide describing startup/service configuration and multiple launch conditions. Used for conceptual separation of configured behavior and observed execution; current-source validation remains required.

**[R4] Apple — Gatekeeper and runtime protection in macOS.** Describes signing, notarization, provenance, and runtime protections. Used to keep distinct security properties and observations separate rather than treating them as a universal safety label.

Sources reviewed for this specification on October 7, 2026.

[R1]: https://developer.apple.com/videos/play/wwdc2020/10168/ "Apple — Explore logging in Swift"
[R2]: https://support.apple.com/guide/mac-help/open-items-automatically-when-you-log-in-mh15189/mac "Apple — Open items automatically when you log in on Mac"
[R3]: https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html "Apple — Creating Launch Daemons and Agents"
[R4]: https://support.apple.com/guide/security/gatekeeper-and-runtime-protection-sec5599b66df/web "Apple — Gatekeeper and runtime protection in macOS"
