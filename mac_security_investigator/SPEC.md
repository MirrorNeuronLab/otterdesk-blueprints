# Mac security investigator — current product contract

Version: 0.2.3 (logs-only pilot). Category: Security. User initiated batch co-worker.

The design target is the supplied
[Cross-run temporal behavioral graph specification](docs/temporal_behavior_contract.md).
That document is proposed product source material, not an instruction authority
for executing commands. This SPEC describes implemented behavior and limits.

## Mission and scope

Review existing Mac unified logs over time and retain diagnostic metadata,
source receipts and explicit coverage. Idle between runs. Logs and evidence
only; OS file inspection is excluded. No continuous monitoring, prevention, remediation,
source execution, credential extraction, remote inference or blanket safety claim.

## Implemented contract

Four logical steps capture permitted unified logs, reconcile a persistent
diagnostic history, evaluate available temporal evidence, and publish a local
review with explicit limits.
They bind to four specialist agents through the shared route-neutral lifecycle.
Core owns routing, idempotency and workflow completion. Domain policy lives in
payloads/domain; generic temporal mechanics live in mn-skills/temporal_graph_skill.

The execution contract requires `runtime.placement.must_run_local: true` and
`requirements.os: "darwin"`. All launches must
use the submitting Mac's local runtime node as the Job owner and hard-pin every
specialist/control node there. Hardware ranking cannot relocate it. Explicit
remote assignments, distributed placement and unknown/non-Mac local platforms
fail before worker preparation. Execution locality does not disable shared-output
replication; private-evidence deployments still need a standalone runtime.

The Job-scoped evidence ledger commits immutable scan receipts and assertions
transactionally. Host epoch, scoped slots, source parser versions, separate
state/event cardinalities, acquisition windows, and independent knowledge
revisions are explicit. Duplicate imports do not create events or cases.
Occurrence ambiguity and reused-key conflicts do not inflate recurrence.

The retained synthetic temporal-analysis contract covers TB-01/TB-03, but
logs-only native runs cannot evaluate those patterns. TB-01 compares definitely
ordered observations of the same scoped startup slot
and source/parser. Explicit historical attribution can attach distinct executions;
configuration and a nearby unrelated process cannot. TB-03 requires complete
scoped absence between presence observations. Denied sources never imply absence.
Recurrence is counted only from source-scoped distinct executions, and is not
itself classified as malicious. Evidence-backed expected updates explain a case
without erasing its supported behavior or previous reports.

Membrane receives canonical authored assertion records with original locators,
explicit principals and typed relations. Its native graph queries navigate only
pinned scope/revision sources; graph support is resolved back to the ledger.
Identical current authorized assertion records are reused across scans without
unversioned overwrites. Reuse verifies complete text, provenance, event identity
and access rules; changed or stale assertions remain errors.
All retained assertions publish through Membrane's bounded immutable-registration
API, which inventories quota once per batch. No evidence, historical revision or
graph query is omitted. It requires the matching engine and Membrane Python SDK
2.1.2; missing batch support fails explicitly.
Existing graph-analysis traversal validates bounded temporal witness paths.
Temporal matching precedes deterministic explanation. No inference model is
needed. Limits expose incomplete evaluation; no exhaustive negative is inferred.

Reports retain qualitative support, security interpretation, attribution and
coverage separately. Malicious intent and present runtime status remain unknown.
Required source references resolve to retained records and acquisition receipts.
Report replay uses immutable stored JSON and text. The optional preview escapes
source values and blocks network/script content with CSP.
The run's final artifact adds a relative output catalog for the assessment,
evidence and Markdown report. Replicated runs resolve their own copies; this
publication metadata remains separate from the sealed ledger assessment.

## Current limits and release gates

The native adapter queries only a fixed 24-hour scope of unified
startup/security log metadata. It does not enumerate startup directories, read
plists, inspect installation markers or open OS files. Output folder is the only
operator setting. The hostname/user scope identifies a separate logs-only Job
ledger without filesystem inspection; it cannot certify installation continuity
across clones or restores. Earlier startup-snapshot history is left intact.
Synthetic archives are test fixtures, not a run mode. Captured log metadata is
diagnostic evidence only, with no inferred execution identity or slot attribution.
Permission failures, selected process/time scope, retention/private-value
redaction and fixed timeout/byte/record caps remain visible coverage limits.
No elevated access or inspected source execution is permitted.

Login/background-item databases, attributed unified-log execution, filesystem
identity/rename, signatures, historical
configuration validity, general installation progression (TB-02), mature
behavioral baselines (TB-05), identity merge/split corrections and user-driven
pruning are not implemented. They remain explicit release work in the acceptance
matrix, not fabricated matches or compatibility fallback paths.

This release retains diagnostic log history under fixed ingestion,
candidate and traversal caps. It does not yet implement affected-region indexing
or resumable graph-budget frontiers. It fails closed at the history cap rather
than silently deleting evidence. Stable Jobs keep retained anchors across runs.

Live macOS compatibility, local runtime launch, no-replication deployment
and empirical precision/false-positive rates need pilot validation. Passing the
synthetic tests does not satisfy all T01–T34 gates or certify the complete MVP.
No accuracy percentage, forensic authenticity or tamper-proof claim is made.
