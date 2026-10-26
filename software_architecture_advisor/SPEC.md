# Architecture Advisor 7.0.2 specification

Local runtime models require at least one GPU with 49,152 MB of GPU memory.
When the selected review model is a registered remote API provider (including
a provider imported from JSON and selected as the runtime default), the host
requires any GPU and at least 16 GB of system RAM, with no GPU-memory, vendor
or driver constraint. Other hardware requirements still apply. Catalog listing,
validation and scheduling use the resolved requirements.

## Outcome

Turn a captured repository into an actionable component/function map and a
traceable focused architecture review. The 23 sections and 150 aspect contracts
in `payloads/report_specs` remain the coverage inventory. Selected aspects get
independent analysis and challenge; unselected applicability remains undetermined
and coverage remains not analyzed. Missing evidence,
failed tasks and capped source packets remain visible; they never imply health.

## Source input

Initial setup asks only for the local source code folder. It is required and
starts empty; there is no sample/default source or additional setup question.
The default model, review goal and focused review policy remain preconfigured.
Advanced command-line configuration may supply a public HTTPS GitHub repository
root URL instead. Exactly one source must be selected. Changing the source
requires a new run.

Capture includes code files only. Documents (including Markdown), JSON/YAML/TOML
data and sample datasets do not enter frozen sources, retrieval, source packets
or model review. Default exclusions include documentation, examples, samples,
fixtures and generated/dependency directories, including Elixir `deps`/`_build`.
Elixir `mix.exs`, code under `config/` and ordinary test code remain in scope.
Explicit graph exports must cite captured code, not ignored documents.
Additional known source formats may be captured for text review without a
structural parser. Operator `ingest.additional_extensions` accepts up to 64
validated source suffixes, excluding documents/data. Capture records the
effective suffix catalog and uncaptured suffix counts. Scope comparison includes
that effective catalog. Capturing a format does not imply semantic support.

The declared BEAM source-analysis skill supplies pinned offline
Tree-sitter parsers for literal Elixir/Erlang modules and syntax dependency
candidates. Python imports retain their existing collector. Source hashes and
exact line spans link each accepted internal edge to frozen code. Syntax-error
files produce warnings and no extracted facts; missing parsers and violated
budgets fail explicitly. Macros, generated modules, preprocessing, dynamic
dispatch, process messaging and supervision topology remain unverified. Other
types, state and control/data-flow layers remain Python-only. Mainstream-language
file components, declarations, include/import dependencies and name-candidate calls
use the declared static-code-analysis skill and retain exact source spans.

## Execution contract

The fixed parent workflow captures source, analyzes dependencies, investigates
architecture through Core-owned child rounds, then publishes the review.
The deterministic planner commits bounded task references. One specialist
invocation performs one OpenCode skill review in OpenShell. Tasks within a phase have independent immutable handoffs; each default round
admits at most two tasks with no serial dependency. Replanning occurs only
after its tasks have terminal durable results.
The planner itself makes no model calls. No worker owns routing or completion.

The parent investigation and its planner use `mn.blocks.bounded_investigation@1`
from the optional SDK component. Direct functions in `domain/catalog_planning.py`
own initialization, admission/planning and terminal policy. The block supplies
ordinary StepSpec/worker boundaries, invocation journals and
validated Core plans. The parent maps its hashed initialization into the `seed`
port; each admitted reviewer receives its original domain `context`, task and
review-input contracts. Core maps the terminal summary reference into the
parent's `result`. Publication verifies the summary and exact terminal-catalog
digest before producing the unchanged report formats. There is no blueprint
initializer/planner agent or investigation StepSpec wrapper. Four parent phases,
the OpenShell reviewer and domain budget ledgers remain unchanged.

The default `focused` profile selects six component/cycle/impact/hotspot/verification/handoff
aspects, their independent challenges, six section syntheses and the executive
review: 19 baseline tasks. It performs no model-based inventory scans. Defaults
are 64 tasks, 32 model attempts, 20 rounds, two tasks/round, two evidence
follow-ups of depth at most two, and 3,600 seconds. Static extraction covers the
captured inventory; targeted model review does not imply whole-repository coverage.

Explicit `full_catalog` mode retains source scans, all 150 analyses/challenges,
23 section syntheses and executive synthesis. Select compatible larger task,
call, round and time budgets. The parent deadline remains a seven-day ceiling.
Calls retain 600 seconds, a 1 MiB output ceiling and 60 KB UTF-8 prompts.
Source packets preserve exact offsets and a 24 KB bound, including Unicode.

## Model selection

SDK `>=1.4.1.dev15` is the minimum runtime contract. Definition creation and
bundle replacement use its bounded submission deadline, with the matching Core
owner-forwarding deadline. This does not change task or model-call allowances.

`opencode.model` is operator-configurable through advanced configuration. Its default
is `mn/default`, the runtime's model selection, including a registered API
default. `mn/<catalog-id>` selects
a particular runtime model. Existing Muse display labels normalize to their
provider/model IDs, which must be registered in the runtime catalog before use.
The SDK owns placement, model preparation and LiteLLM route resolution. The
initializer freezes its non-secret gateway descriptor before admitting tasks;
OpenCode uses that exact route inside OpenShell. No direct-provider or paid-model
fallback is used. The old direct `opencode.spark_base_url` setting is rejected.
The sandbox permits only OpenCode's chat-completions requests to the authorized
Mini and Spark gateways. Other deployments require an exact endpoint policy
change through `opencode.gateway_hosts`. SDK and CLI render the policy bindings
before provisioning and staging. Host OpenCode configuration and credentials
are never copied.

OpenCode's numeric step receipts include cached input and reasoning output.
Core commits them with the review artifact; owner reconciliation appends them
to the SDK run ledger with stable call identities before finishing the domain
receipt. Replayed commits count once in analysis. Invalid JSON does not discard
measured model usage. Missing provider receipts remain unmeasured; accounting
makes no extra tokenizer requests and does not certify missing coverage.

## Evidence and content

The bundled catalog validates every aspect file against its original SHA-256.
The context pins catalog digest, source manifest, configuration and objective.
Source inventory equality and hashes are verified on load and publication.
Models select supplied evidence IDs; the worker resolves those to exact frozen
file hashes, character offsets, line ranges and excerpts. Invented or out-of-scope
citations and unresolved report IDs are rejected. Source is never executed.

Aspect prompts contain the full applicable specification, shared conventions,
and a requirement-by-requirement answer contract. Prior validated results and
source spans are selected within a hard prompt bound; whole omitted records are
counted. Challenges receive the corresponding analysis and other evidence.
Section and executive synthesis use bounded prior results, with omissions
reported. Inferred summaries retain their source task references.

Claims distinguish observed, derived, inferred, assumed and proposed information.
Confidence includes rationale and remains separate from priority, urgency,
effort and impact. Recommendations and work packages are created only from
model-proposed, validated, traceable records; missing recommendations are not
replaced with automatic generic remediation. Unresolved challenges require
verification before implementation. Runtime measurements and actual test runs
are never inferred merely from source presence.

## Durability and failure semantics

SDK committed artifacts protect plans/results from conflicting rewrites.
Task request identities and SQLite attempt reservations make duplicate delivery
safe; an interrupted attempt cannot automatically consume another model call.
Core supplies the execution barrier and durable shared run directory. OpenShell
synchronizes shared artifacts through Core's storage contract. No separate host
copy or native execution fallback is implemented by the blueprint.
Malformed/model failures are blocked task results, while corrupted committed
artifacts fail validation. Offline mode explicitly requests static-only analysis:
the planner retains unassessed tasks but dispatches no model-review children.
It publishes not-analyzed coverage without preparing task prompts or provider
requests. Partial
reports state the terminal reason, task status and source omissions.

## Interactive workspace and cumulative output

The final publication phase produces real source-linked JSON, Markdown and an
offline interactive dashboard from the same validated records. `outputs.job_files`
declares `data`, `reports`, `web` and `web_ui.json`; SDK host delivery places them at the configured Job
folder root (`~/Downloads/software_architecture_advisor`) and leaves ordinary
audit outputs in their standard run folders. The blueprint does not derive host
paths or perform a separate data/web host copy.

The declared mutable `architecture_results` Job resource owns append-only
snapshot records and pages. An atomic latest index is separate from immutable
publications. Same-run replay verifies its projection digest, cannot duplicate
history, and cannot roll back a newer snapshot. Different Jobs remain isolated.
UI composition belongs to focused domain modules and bundled local assets;
there is no dashboard service, entrypoint or runtime health dependency. The web
artifact is required by this product contract: failure remains explicit with
already-published data/Markdown preserved.

The UI extension enables `static_html` output in the conversation workspace.
Publication registers and delivers `web_ui.json` with the report page, including
its verified byte count and digest. The existing runtime proxy serves the page;
the blueprint starts no service and changes no runtime behavior.

Version 3.8.2 also selects the complete published `report.md` and the section
Markdown produced by that publication as conversation sources. The declared
document-conversion skill writes complete Markdown and provenance receipts in
run-keyed `context_sources/outputs/` under the SDK-provided Job output folder.
Captured originals, task audits, drafts and budget ledgers are not selected.
Source publication is required before the report worker returns. SDK
>=1.3.58.dev86 provides whole-section selection under the existing allowance;
omissions remain explicit and chat cannot initiate reviews or implementation.

The webpage includes overview, findings, file/function relationships,
source evidence, dependency matrix, cyclic groups, Git co-change, structural
hotspots, prior-snapshot hash changes, bounded reverse dependency paths, gaps,
proposed checks, recommendations and engineering work packages. Every accepted
structural edge is rejoined to frozen source hashes and valid physical spans.
Counts disclose their units. Co-change selections expose the matching commit set,
both directional denominators and union denominator. Missing history is unavailable,
not zero. Graph tables provide an equivalent keyboard-operable access path.

Model finding annotations request question, affected capability, mechanism,
consequence, priority rationale, next decision and closure condition. Supplied
annotations are bounded and validated, preserved in JSON and Markdown and shown
alongside counterevidence. Missing older annotations are explicitly unavailable.
Assessment, evidence basis, review and resolution remain separate dimensions.

The overview must lead with a grounded next action, a proposed benefit and a clear
desired result. Publish copyable coding-tool prompts in the main Markdown/JSON,
standalone prompt artifacts, work-package Markdown and the dashboard. Generate
investigation, planning and verification handoffs from real retained records.
Implementation handoffs require a supported, scoped work package with resolved
challenge gates; missing evidence cannot turn a structural clue into a refactor.
Preserve baseline hashes, counterevidence, alternatives, constraints, checks,
acceptance and stop conditions. Require reassessment against the current checkout,
preserve unrelated edits and distinguish actual test outcomes from proposals.
Expected benefits remain proposed, never invented measurements. Copy/export
does not run a coding tool or authorize automatic implementation.

Use one domain-owned prompt representation across all delivery formats. Keep
source context whole and bounded; disclose omitted records and their retained
artifact, and withhold implementation prompts when their context is incomplete.
Retain prompt artifacts per snapshot. Browser clipboard failure must leave a
selectable complete prompt, without remote clipboard services or third-party page requests.

Cross-run comparison requires the same repository identity; local repositories
without a canonical origin need an explicit `ingest.repository_id`. Different
capture exclusions or analysis settings invalidate direct metric comparability.
A disappeared finding is not verified resolved. Conservative finding continuity
uses wording, paths and aspects; rename or interpretation changes can need
manual reconciliation. Before/after panels contain actual retained cited excerpts
and source hashes, not reconstructed semantic diffs. Traversal is capped at
100 changed roots, four hops and 128 nodes per root with an explicit frontier.

Review drafts and saved views stay in browser storage. An explicit bounded
`inputs.payload.review_file` imports attributable, revision-bound decisions into
Job history. Changed material causes reassessment; conflicting reviewers remain
visible. Source, deployments and remediation status do not change upon acceptance.
Export is a local copy, not implicit publishing. CSP permits only sibling/same-origin report data and bundled local assets
and active source content; data is JSON-escaped and excerpts render as text.

Current limits: one repository per run; structural support includes Python imports/AST, BEAM dependencies and
the 13-language file/include/import/call candidate adapters at their documented levels; unsupported captured formats retain text review. Semantic contract compatibility,
PR baseline selection, imported runtime/check results, policy enforcement,
deployment/state/workflow modeling, performance/capacity prediction, permission-
filtered sharing and webpage natural-language answers are not implemented.
Their absence must remain visible and cannot be represented by synthetic data.

## Deliverables and acceptance

Version 7.0.1 publishes the current frozen `data/`, `reports/`, `web/` and
`review_index.json` files through SDK `publish_files` and `deliver_files`.
Required delivery registers receipt-verified run downloads before publication
can complete; failures remain retryable without repeating captured research.
The SDK owns batching, byte verification, atomic delivery and the output index.
Captured source, confidential `catalog/` audit and SQLite budgets are not public
downloads. Explicit run-only delivery preserves existing product-owned host
exports and cumulative Job history. SDK >=1.4.1.dev15 supplies that destination
contract; OpenCode skill >=1.4.1.dev2 supports endpoint-free fake model bindings.

Publish report Markdown/JSON; selected section files (23 in full-catalog mode); coverage for 150 aspects and
all source packets; canonical evidence, claims and findings; recommendations,
assumptions, verification tasks, roadmap and proposed implementation work
packages. All material record references must resolve. All cited source spans
must match captured bytes. Work packages contain baseline, actual files,
evidence, constraints, non-goals, migration steps, tests, acceptance and stop
conditions. Report generation does not authorize implementation.

Tests must exercise more than 300 tasks using actual SDK child-plan contracts,
round barriers, dynamic work, final executive ordering, replay, failure/budget
handling, Unicode bounds, exact citation validation, all aspect/section outputs
and report tampering. A small opt-in live OpenShell test verifies the default
OpenCode provider without launching hundreds of external requests.

## Limits

Static source review is not runtime measurement, a security audit or a guarantee
of architectural correctness. Language-specific structural extraction may be
incomplete; the text reviewer can still assess supported polyglot source.
Bounded relevance selection may miss cross-cutting interactions. Unknown or
omitted evidence must remain explicit. OpenShell shared-storage transfers are
serial and may dominate runtime for very large captured source inventories.

The packet reviewer uses an explicitly built OpenShell image context at
`payloads/openshell_worker`, including `iproute2` for isolated networking.
SDK image preparation installs declared dependencies before sandbox creation.
The reviewer imports uploaded blueprint modules from its invocation workdir.

Parent-phase Docker workers use a single-stage Python 3.12 image without
`USER` instructions, allowing SDK skill-preparation hooks to add native tools.
OpenCode and sandbox system setup belong to the separate OpenShell image.
Docker workers inherit their logical step timeout instead of sharing a one-hour
cap. Source initialization uses the seven-day investigation window; planner
invocations retain their 3,600-second control and packet reviews their 720-second
worker limit.

### Immutable review handoff

The owner planner persists stable tasks, bounded prompts, evidence selections,
configuration, and SQLite reservations before dispatch. Pending reservations count
toward `max_calls`; ambiguous execution is never automatically refunded. Frozen
admission JSON is published with the runtime run ID through SDK artifact helpers.
Reviewers use isolated attempt workspaces and publish task-specific result files.
They have no writable budget database or owner catalog mirror. The next owner
planning pass reconciles only Core-committed result receipts, verifies citations
against the frozen owner snapshot, then publishes domain receipts idempotently.
Independent immutable handoffs allow bounded concurrent tasks within each phase;
round and phase barriers remain unchanged.

Owner publication exports the validated report, section documents, work packages, and JSON task audit to the declared output folder. SQLite reservation state is excluded from that export.

Admitted review tasks carry descriptive source, aspect, or synthesis labels in the child-workflow monitor. Malformed JSON, provider errors, and invalid model evidence become durable blocked task results with no accepted claims; later tasks continue. Input integrity and committed-artifact identity failures still stop execution.

## Filesystem runtime memory

`text_memory.enabled=true` uses authenticated Membrane TextMemory v1 and
CompileEvidence v2. Complete frozen or preprocessed input text is committed to
run-scoped Markdown with upstream source hashes. Decisions become immutable text
observations. Retrieval preserves whole dependency bundles within
`text_memory.max_context_bytes`; complete witnesses stay in run artifacts and are
excluded from model prompts. Historical memory is navigation, not legal or source
evidence. Required context still needs verified full-request token admission.
Set `text_memory.enabled=false` for an explicit memory-free profile. No retired
FileMemory adapter or automatic migration is provided.

## Retry budget and evidence contract

Manual Core checkpoint retry preserves completed logical steps/child tasks and
uses the original workflow and source inputs. Required domain metadata declares
only bounded retry-adjustable budget/timeouts. Owner-local domain steps declare
idempotent internal writes; OpenShell review execution requires verified handoff
state before replay. Completed model requests use committed domain receipts;
uncertain attempts remain blocked.

Domain retry helpers apply explicit effective allowances and subtract durable
run-wide consumption. Frozen source capture, investigation context and request
artifacts remain immutable evidence. A replayed source-capture boundary verifies
its committed request and snapshot instead of ingesting the source again.

## Context engine contract

This release declares `mirrorneuron-python-sdk[context]` in `dependencies.json`. Worker preparation requires the Membrane v2 client (>=2.1.0,<3); local source mode stages its matching source project. `mn.context` declares the Markdown profile, and `text_memory.enabled=false` explicitly disables recall. The context service stores Markdown revisions with one disposable DuckDB per job and uses CPU only. Set `MN_CONTEXT_ADDR` and `MN_CONTEXT_AUTH_TOKEN` through trusted runtime settings. Optional `MN_CONTEXT_OBSERVABILITY=true` logs authorized source and context content. No model compressor, Redis memory, or automatic migration is required.

Historical runtime recall uses native filesystem passages with exact supporting
handles, bounded separately from the current task and source evidence. Structural
graph queries continue through the source-backed allowlisted views; each query
and canonical witness is retained in the catalog audit. Runtime notes cannot
replace a graph query or establish source claims.

Version 3.5 selects relevant existing graph views alongside typed path
queries. Retry/idempotency questions request call-to-state, test-to-call and
control-flow views. Model-facing rows carry exact supplied source-witness IDs;
rows whose complete witnesses are omitted cannot survive prompt assembly.
Full source-backed receipts remain in the catalog. This is bounded static
discovery and does not establish runtime correctness or exhaustive coverage.

Claims explicitly classify counterevidence as supplied, not found in the searched
scope, or unknown. Supplied counterexamples require exact visible source
citations, validated and retained through the final claim/finding registers and
Markdown publication. An unexamined counterexample remains unknown.

### Version 3.4.1 source and runtime separation

Publish byte-exact frozen input originals in the separate source corpus with
source SHA-256, snapshot provenance and explicit source-query authorization.
Trusted Python AST locators produce complete static definitions/imports.
Syntax-unavailable inputs remain queryable as native text with an explicit
limitation; no fabricated structural facts are permitted. Persist original
publication/query bindings separately from runtime records, and revalidate
authorized current revisions before reusing cached source spans. Model-visible
source evidence retains exact physical span-derived S- citation identities.

Publish validated review outcomes as authored runtime Markdown. Scalar Facts
enable typed DuckDB recent queries; Notes retain complete nested claims and
qualifications. Original excerpt bodies are excluded from runtime notes while
their source locators remain intact. Bind publication clocks before writes and
filter recall by review family, source snapshot and relevant aspect. Original
witnesses and complete prior claims precede optional historical navigation in
prompt admission. Omit whole records with explicit counts/status; never truncate
source definitions to meet a byte bound. Retain paired 8,192/32,768-byte checks.
The existing full prompt byte limit is separate from verified model tokens.
Declare the authored review query schema before first recall. A schema record is
a constraint with a distinct family, never an observation or supporting finding;
the review-family filter must exclude it from empty and populated histories.
Use actual remaining full-prompt byte capacity for whole source witnesses rather
than a fixed fraction. Preserve frozen retrieval packets during admission; source
omissions and graph rows whose supporting spans do not fit remain explicit.

### Atomic support admission

Use the Membrane SDK support-group helper in the active catalog assembler.
Graph rows and prior claims carry all exact source and counterevidence witnesses
as one component; shared witness identities join components transitively.
Admission tests complete rendered groups in query priority order. Never retain
an exclusive partial witness of an omitted group. Unrelated complete source
candidates are optional. Exclude witnesses of graph rows removed before caller
admission. Retain complete prior results or omit them whole, with capacity counts.
Unresolved graph support cannot create a visible relationship. Duplicate immutable
source identities must have identical bodies or fail. Frozen requests preserve
detailed group receipts; model-visible status distinguishes complete, incomplete
and insufficient-capacity support. UTF-8 byte accounting does not replace verified
serving-token admission and does not establish answer correctness.

## Persistent file identity and selective memory

File identity belongs to the shared graph-analysis skill. Initial entity UUIDv5
uses repository identity and normalized relative path; SHA-256 tracks raw content
versions independently. Snapshot capture serializes identity reconciliation and
publishes its registry only through a successfully checked snapshot's CURRENT
pointer. File nodes and DECLARED_IN links survive lazy graph publication. Trusted
Git rename hints precede unique disappeared/new exact-content matches; copies,
ambiguous candidates and unresolved moves never merge automatically. Current and
historical paths preserve repository case. Existing parser-owned module/symbol
IDs and revision-qualified evidence IDs remain unchanged. Existing snapshots
remain readable and need a new capture to adopt file identities; preserve the
identity registry to retain rename history across rebuilds.

Optional runtime recall is admitted only for aspect_analysis/aspect_challenge.
Source scans, evidence_followup, section_synthesis and executive_synthesis carry
self-contained current packets and do not open the memory service for recall.
# Query-derived local static support

Use the optional Python adapter >=0.1.3 with Membrane SDK >=2.1.0. Named source
queries protect complete local helper/binding/guard/enclosing-section dependencies
under the same pinned original revision. Preserve all static rebinding alternatives;
never fill absent imported implementations or configuration values. The v3 source
publication identity fences earlier cached selections. Required local support still
passes whole-context admission and may report insufficient capacity. Runtime
history recall remains limited to aspect analysis and challenge tasks.

## Whole-unit discovery and typed paths

Use exact structural bindings first and native whole-unit lexical/hybrid search
otherwise. The optional hybrid encoder covers every byte using pooled pieces;
source SHA-256, revision and embedding configuration bind publication. Preserve
the complete selected root and transitive local support atomically, including
ranked roots. Return explicit missing/capacity coverage instead of a signature or
partial body. Non-Python and syntax-unavailable files use structural text units.

Bind graph seeds to exact module/file identities and retrieved original spans.
Use the shared graph skill's typed bounded traversal with a native RGX adjacency
callback. The blueprint owns relation selection, authorized scope, source joins
and static-coverage qualifications. Retain ordered edges and complete endpoint
declarations. No automatic cycle view or fixed two-module/three-view shortlist is
allowed. Default bounds are 12 seeds, four hops, 128 nodes and 128 edges; the
existing query allowance also applies. Unknown entity bindings remain unresolved.

Hydrate all path witnesses to original structural units and their dependencies
before final support admission. Remove the independent graph byte cap; apply the
actual final prompt allowance to complete support groups. Detailed native
receipts stay in the catalog. Omitted or partially indexed paths cannot establish
absence, and static edges cannot establish runtime execution. Existing catalogs
require a fresh source publication; file identity reconciliation is unchanged.


Final context verification is experimental and defaults to
`text_memory.quality_verification=false`. For manual validation in a new run, set
`--set text_memory.quality_verification=true`. Required original-source packets
then receive explicit binding/support checks and at most one bounded retrieval
repair within their authorized scope. Missing required support produces an
explicit inconclusive/blocked result before model dispatch; optional runtime
notes may be omitted. Full witnesses stay in run artifacts. A passing witness
does not prove semantic sufficiency, exhaustive discovery or the truth of a
model answer. Initial Laya problem classification remains independent.

The October 5 paired source trial improved legal excerpt retention but did not
reduce strict unsupported/nonconforming answers; it therefore failed the
reliability-first default-rollout rule. The switch remains off pending improved
source selection and a successful prospective evaluation. This change does not
deploy or reset a runtime.

## Shared capability ownership

Exact citation hash, offset, excerpt and line checks use the SDK RAG verifier. Architecture claim policy, allowed-source scope and report composition remain blueprint-owned.

## Standard MCP supervision

This package requires `mn.mcp.supervision.v1`. The SDK implements the shared manual, capabilities, context, results, activity, lifecycle, and operation tools. `knowledge/user_manual.md` is bundled with the prepared Job. Domain tools and their native JSON input/output schemas are declared once in `extensions/mcp.json`; response agents derive their bindings from it. All tool results use `mn.mcp.tool_result.v1`. Mutations require a request ID, and asynchronous work is observed through `get_operation_status`. Upgrade the installed SDK/API/desktop together and update idle Job definitions before using this contract.

The review LLM is declared through the runtime LLM extension. Registered API
defaults are projected onto the selected node's LiteLLM gateway without
preparing a local chat model. OpenShell uses that node's advertised gateway
address; managed local model selections retain SDK first-use preparation.

Git provenance capture disables optional Git locks so staged input indexes remain byte-identical and checkpoint recovery can verify the original input inventory.

The catalog planner has a bounded one-hour control deadline: a full 64-task admission batch can exceed five minutes while compiling revision-bound source and graph evidence. Completed admissions remain durable across checkpoint recovery.

## Static code and function evolution contract

Declare `mirrorneuron-static-code-analysis-skill`; reusable parsing, graph metrics
and batched Git mechanics live in `mn-skills`. Blueprint modules own focus policy,
evidence-graph adaptation, model-context selection and report presentation.
No runtime, SDK or worker-lifecycle implementation changes are required.

`data/static-code.json` contains file components and directory groups,
separate include/call edges, functions, unresolved call sites, cycles and degrees.
`data/function-evolution.json` contains anchored added/modified/deleted
function events, before/after blob IDs and exact source spans, version edges,
call-name changes and co-change pairs. `web/code-map.html` is a data-driven,
interactive view with keyboard-operable graph controls and equivalent tables;
`reports/code-map.md` is its concise review brief. The dashboard links the map,
and host output copies include these artifacts. No source code executes.

History uses three bounded Git processes and cached unique-blob parsing, with no
checkout or per-file Git subprocess. Defaults are 80 first-parent
commits, including merges compared against their first parent, capped by captured `ingest.git_commits`, and a 30-second deadline.
Tune `analysis.history_commits` and `analysis.history_timeout_seconds` explicitly.
Historical parse gaps, bounded/shallow windows and omitted co-change pairs remain
visible. Function/file renames are not inferred; syntax edits include comments
and formatting. Dirty captured source is distinct from anchored committed history.
Missing history means unavailable, never zero churn or proof of original creation.

Source-query retrieval defaults to `lexical`; no embedding calls are needed for
this path. Optional `hybrid` retrieval remains available when semantic discovery
justifies its indexing cost. Current model evidence uses whole function/callee
support groups and exact S- source spans through the existing atomic admission.
Historical JSON is a separate evidence basis and cannot masquerade as current
source citations. Static candidates are not runtime traces, causal explanations,
risk scores or measured business impact. A tech lead must verify build-dependent
and indirect relationships before acting on proposed changes.


## External data rendering and dynamic growth graphs

Published content is separated by role: `data/` contains JSON, `reports/`
contains Markdown, and `web/` contains reusable HTML shells, JS, CSS and the
bundled D3 license. No source/review payload is embedded in HTML. Normal HTTP
rendering reads only sibling same-origin data. File-mode rendering explicitly
loads user-selected JSON and rejects mixed snapshot identities. Downloaded
reports retain correct links to their matching archived data and graph.

The D3-only explorer provides a DSM ordered by directories, file-level SCCs or
coupling; a dependency neighborhood; a source-size/change-activity treemap; a
bounded reverse reachability view with evidence paths; and a co-change matrix
with denominators and exact contributing commits. Absent approved rules, no
layer violation is asserted. Complexity, code health, severity and behavior
are not inferred from degree, size, churn, cycles or co-change. Matrix output
is bounded to 80 entities with explicit omitted counts. Impact traversal stops
at four hops/128 entities and draws at most 32, retaining reached paths in a table.

The timeline reconstructs whole selected committed trees, including unchanged
and historical deleted supported paths. First-parent merges compare with their
first parent. Shared immutable definition/call/relationship records back graph
frames, timestamps, subjects, growth metrics and baseline comparisons. Parse
gaps are retained and excluded from inferred removal counts. Source paths,
blob IDs, hashes and spans remain available for audit. Committed source is
separate from a dirty captured worktree. Stable dependency-neighborhood slots
preserve orientation through time. All chart values have tabular access.

Repeated captures of the same Job append metrics to `data/growth.json` with
scope/method comparability and deltas; different Jobs remain isolated. This
uses the existing capture/scheduling contract, with no runtime or watcher changes.
JSON snapshot history and Markdown snapshot history have distinct roots; prior
snapshots are never recursively nested inside a new snapshot. A repeated old
publication cannot replace the newest graph or growth record.

Focused model analysis has six topics and 19 baseline tasks with two tasks per
round; completed waves are challenged promptly. Two consecutive provider errors
or timeouts terminate further model admissions with explicit partial status.
Deterministic growth and graph evidence remains useful without an executive
model response. Unselected catalog topics remain in coverage and do not create
verification tasks. Blocked model responses require a reason; strict source
validation and independent challenge gates remain in place.


History budget exhaustion preserves current source facts and publishes explicit
unavailable history with the exact bound that stopped it. It does not silently
shorten the window or report zero churn. Invalid/corrupt Git objects and invalid
configuration still fail. Reduce the requested history window for fact/blob/byte
limits; increase the time allowance only for deadline exhaustion.

## Coordinated result page

For syntax-graph publications, `web/index.html` and `web/code-map.html` render
the same result page with eleven focused tabs: Overview, Dependency graph,
Dependency matrix, Call paths, Change impact, Graph evolution, Changes together,
Size and churn, Recommended prompts, Architecture score, and Evidence coverage.
Each chart has a single purpose and no nested visualization switcher. Only files
and functions are selectable entity levels. Directory aggregation, directory
matrix ordering and directory treemap groups are absent. Source paths retain
identity; underlying scoring policy and immutable saved records are unchanged.
The opening tab contains one lead action, findings/weaknesses, up to two prompt
previews and a compact coverage link. Detailed score, evidence coverage and
history transitions live in their relevant tabs. Expandable rows below each
chart contain selected-entity evidence, exact records and interpretation notes. The opening view names a measured
inspection candidate and the limits of model review. Presentation uses local
assets, thin rules, restrained color and progressive disclosure. The advanced
review register remains available for saved review decisions and comparisons.
Archived pages bind to their own immutable data, report and review register.
Content-derived asset query identities prevent stale cached scripts/styles from
being combined with refreshed HTML shells.

Graph evolution is a network playback, not only a chart of code counts.
The renderer maintains one bounded committed-union layout per entity level,
relationship filter, scope and algorithm. Organic is the recommended default;
users can switch to Sequential or Radial. Organic uses seeded multilevel D3 force
refinement; Sequential uses strongly connected groups and barycenter ordering;
Radial uses minimum undirected distance from the selected entity. Switching
algorithms preserves the graph and source selection. No directory groups or
architectural communities are inferred. Canvas renders nodes and edges with
adaptive labels; D3 zoom and quadtree picking retain direct inspection. There is
no layout-motion animation during playback. Selected/baseline nodes
and edges are overlaid with explicit additions, removals, changed definitions
and unknown gaps. Views disclose the 10,000-entity / 50,000-relationship limits,
including exact omitted counts. Connected/all/two-hop scopes include the selected
entity, and a native selector plus keyboard-operable tables preserve
relationship evidence and definition changes beyond the visible network.
HTTP layout work runs in a cancellable worker with a 20-second limit and a bounded
result cache; offline file mode runs the same algorithm on the main thread. Worker
failures remain explicit. Neighbor selection and algorithm changes must not modify
source evidence or dependency identity. Browser rendering uses only bundled D3 and
local source assets; no commercial graph SDK or runtime change is required.

Function call paths show bounded callers/callees and source-backed witness
routes (two hops per direction, 32 functions). They must be labeled candidate
call navigation. They do not claim program slicing, data-flow completeness,
execution order or runtime timings. Community discovery, conformance, true
program slices and execution views require their own validated evidence; none
may be inferred from directory names or static reachability alone.

Saved JSON and Markdown are immutable. HTML shells are derived presentation and
may be regenerated for retained snapshots when shared JS/CSS changes, preserving
the original snapshot identity and evidence paths.

## Mainstream language and scoring contract (4.2)

The reusable syntax skill now extracts named definitions and same-file call
candidates for 13 mainstream languages: C, C++, Python, JavaScript, TypeScript,
Rust, Go, Java, C#, Ruby, PHP, Kotlin and Swift. JSX/TSX and Node ESM/CommonJS
variants are included. Literal local import candidates are distinct from
includes and calls; external/ambiguous paths and compiler/type binding remain
unknown. Go/Java/C#/Kotlin/Swift cross-file linking is not assessed. Per-language
coverage and binding scope are retained, and extractor version changes must
break growth comparability. This is not universal language/compiler support.

Every new static publication exports `data/architecture-score.json` and
`reports/architecture-score.md`. The custom `advisor-structural-v1` model allocates
25 points to modularity/cohesion, 25 to dependency health/cycles, 20 to change
isolation, 15 to data ownership and 15 to rule conformance. Exact ratio formulas,
inputs, evidence basis, unassessed weights, parse coverage and limitations are
published with the result. Unknown dimensions are not normalized away or given
zero/full credit; an incomplete score is a provisional possible range out of
100. Default runs do not assess ownership or rule conformance. Supplemental
measurements require complete nonempty counts, matching captured hashes/spans
and approved rule IDs for conformance; these remain caller-declared evidence.
The model is not an ISO/SIG calculation, a defect score or a readiness gate.

The first tab foregrounds recommendations and their verification status,
reported findings, structural weaknesses needing investigation, evidence gaps,
copy-ready scoped prompts and score coverage. A dependency cycle must not be
presented as a confirmed software mistake. Older saved publications without a
score stay viewable and explicitly show that no score is available.
The headline favors a measured investigation until a work package has supported
findings, complete prompt evidence and a permitted implementation handoff.
The Overview surfaces up to three measured adjacent topology transitions,
excluding relationships and definitions incident to parser gaps. Replay selects
the changed entity, file/function level and previous-state baseline. This is
graph navigation, not a semantic change or defect verdict.
When static cycles exist, their focused analysis precedes broad mapping.
Current static function evidence must bind graph-query scope even when optional
memory/original-corpus search is disabled. Application-structure questions favor
cross-file application candidates; test-specific questions favor tests. Prefer
distinct source files in the bounded function selection. Unsupported formats
retain physical size without acquiring parsed structure (`syntax-3`).
Hotspot history must distinguish unknown from zero. Out-of-scope entities are
grey; partially measured function counts are marked as lower bounds.

## Native block composition (7.0.0)

All six entrypoints are direct `(block, inputs)` domain functions. Capture and
structural analysis publish immutable evidence packets bound to original config,
Job/run identity, source bytes and derived facts. Catalog initialization verifies
that authority; planners return bounded domain tasks to the shared investigation
block. Core remains the only child scheduler and completion owner.

The owner-only catalog binds the structural packet by digest without exposing its
ledger to reviewers. Packet reviews use the stock SDK worker and standard
OpenShell handoff. Reconciliation validates task/request identity, usage receipts
and exact source citations before accepting results. Publication requires the
matching terminal summary and captured evidence, preserves required UI failures,
and uses SDK artifact/file APIs. Original/effective settings and Job storage come
from the native SDK context; no runtime-context dictionary or alternate local
hypothesis runner remains. OpenShell remains optional per worker; the other
phases retain Docker execution.

The retired unregistered hypothesis implementation and its exclusive tests are
removed. Named graph queries, source support/counterevidence, source safety,
focused/full-catalog policies and history/review-import tests remain. The current
suite covers the actual compiled native bindings, including zero model calls for
explicit static-only requests, tampered-source rejection and interrupted required
publication. SDK >=1.4.1.dev15 and blocks >=1.3.61.dev38 with matching native-context/OpenShell
support are required. Offline tests do not qualify the RGX binary, live gateway,
provider, policy provisioning or multi-node execution.
