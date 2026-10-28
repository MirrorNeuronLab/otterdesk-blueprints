# Mac security investigator — current product contract

Version: 0.2.4 (logs-only pilot). Category: Security. User initiated batch co-worker.

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
They bind to four stock domain-operation blocks with explicit domain hooks.
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
2.1.3; missing batch support fails explicitly.
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

## Standard MCP supervision

This package requires `mn.mcp.supervision.v1`. The SDK implements the shared manual, capabilities, context, results, activity, lifecycle, and operation tools. `knowledge/user_manual.md` is bundled with the prepared Job. Domain tools and their native JSON input/output schemas are declared once in `extensions/mcp.json`; response agents derive their bindings from it. All tool results use `mn.mcp.tool_result.v1`. Mutations require a request ID, and asynchronous work is observed through `get_operation_status`. Upgrade the installed SDK/API/desktop together and update idle Job definitions before using this contract.

## Native block composition (3.0.0)

Capture, reconciliation and investigation consume the SDK block context and
committed input references directly. The final phase uses the stock
`report_publication` block for required JSON/Markdown and an optional HTML view.
There is no operation wrapper, context adapter, local renderer or local publisher.
The temporal ledger still seals domain assessments; v3 stores its ReportDocument
projection under a distinct presentation identity so older reports remain sealed.

The optional preview uses the shared escaped layout and a bounded timeline table.
It retains acquisition/time uncertainty, first-known revisions, witnesses and
source references. CSP permits only bundled hashed UI scripts and blocks network
connections and untrusted scripts. Preview rendering failures are recorded in the
stock publication receipt and cannot prevent authoritative JSON/Markdown output.
Rendering and aggregate block records have explicit shared capacity limits; a
capacity failure is visible, without silently truncating evidence.

This requires `mirrorneuron-web-report-skill >=1.3.61.dev4,<2` in addition to the
declared SDK/block packages. Worker execution remains HostLocal on the submitting
Mac. The empty runtime/agents/steps directories are SDK upload-layout placeholders,
not Python entrypoints or compatibility adapters.


## Stage-aware conversation

OtterDesk reads `payloads/prompts/conversation.json` as optional app-owned guidance. It combines this role and stage policy with the pending question, confirmed non-secret setup answers, recent dialogue, selected report and fresh Job state. Short follow-ups retain their topic; a correction does not silently change saved configuration.

Use Memory or explicitly ask to remember, edit or forget an explanation preference. This affects Chat wording only; working rules and evidence keep their existing domain controls. The optional `inputs.payload.supervisor_instructions` array is app-managed, never a required setup answer or a new workflow permission.

Private assertions and temporal provenance stay in the existing local Membrane and sealed ledger. Do not copy their content into Chat or preference memory. Chat receives capabilities only. Never infer private findings, ask for raw logs, certify a Mac is safe, inspect OS files, request elevation or remediate. Open the local saved report to review private evidence. Existing submitted runs retain their configuration, evidence and approvals. An idle prepared Job may refresh through the existing conditional API without rehiring, resetting memory or mutating an active run.
