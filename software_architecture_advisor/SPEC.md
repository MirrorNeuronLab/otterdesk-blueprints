# Architecture Advisor 3.8 specification

## Outcome

Turn a captured repository into a traceable architecture review covering the
23 sections and 150 aspect contracts in `payloads/report_specs`. Every aspect
gets an applicability decision independently of coverage. Missing evidence,
failed tasks and capped source packets remain visible; they never imply health.

## Source input

The default source is the public repository
`https://github.com/MirrorNeuronLab/MirrorNeuron`. Supply exactly one public
HTTPS GitHub repository root URL or local source folder. Clear
`inputs.payload.repository_url` when choosing `inputs.payload.input_folder`.
Changing the source requires a new run.

Capture includes code files only. Documents (including Markdown), JSON/YAML/TOML
data and sample datasets do not enter frozen sources, retrieval, source packets
or model review. Default exclusions include documentation, examples, samples,
fixtures and generated/dependency directories, including Elixir `deps`/`_build`.
Elixir `mix.exs`, code under `config/` and ordinary test code remain in scope.
Explicit graph exports must cite captured code, not ignored documents.

The declared BEAM source-analysis skill supplies pinned offline
Tree-sitter parsers for literal Elixir/Erlang modules and syntax dependency
candidates. Python imports retain their existing collector. Source hashes and
exact line spans link each accepted internal edge to frozen code. Syntax-error
files produce warnings and no extracted facts; missing parsers and violated
budgets fail explicitly. Macros, generated modules, preprocessing, dynamic
dispatch, process messaging and supervision topology remain unverified. Other
automatic syntax layers remain Python-only and declare that limitation.

## Execution contract

The fixed parent workflow captures source, analyzes dependencies, investigates
architecture through Core-owned child rounds, then publishes the review.
The deterministic planner commits bounded task references. One specialist
invocation performs one OpenCode skill review in OpenShell. Each round is serial
and replanning occurs only after its tasks have terminal durable results.
The planner itself makes no model calls. No worker owns routing or completion.

The planned content consists of source scans, 150 aspect analyses, 150 independent
challenges, bounded dynamic evidence follow-ups, 23 section syntheses and a final
executive synthesis. Defaults: 1,024 total tasks and model attempts, 20 rounds,
64 tasks/round, 64 follow-ups of maximum depth two, and 604,800 seconds (one week)
for both the parent investigation deadline and planner walltime budget. Capacity
is reserved for synthesis; remaining source omissions are recorded. Each call
has a 600-second timeout, 1 MiB output ceiling and 60 KB UTF-8 prompt bound.
Source packets have exact offsets and are at most 24 KB, including long Unicode
lines. A run can stop earlier for budgets and still publish a partial report.

## Model selection

`opencode.model` is operator-configurable and exposed in setup. Its default
is `mn/default`, the runtime's local model selection. `mn/<catalog-id>` selects
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
artifacts fail validation. Offline mode explicitly means not analyzed. Partial
reports state the terminal reason, task status and source omissions.

## Interactive workspace and cumulative output

The final publication phase produces real source-linked JSON, Markdown and an
offline interactive dashboard from the same validated records. `outputs.job_files`
declares `data` and `web`; SDK host delivery places them at the configured Job
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

The webpage includes overview, findings, directory-based architecture groups,
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
selectable complete prompt, without remote clipboard services or page networking.

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
Export is a local copy, not implicit publishing. CSP blocks page network access
and active source content; data is JSON-escaped and excerpts render as text.

Current limits: one repository per run; structural graph support is Python and
BEAM, with text review for other languages. Semantic contract compatibility,
PR baseline selection, imported runtime/check results, policy enforcement,
deployment/state/workflow modeling, performance/capacity prediction, permission-
filtered sharing and webpage natural-language answers are not implemented.
Their absence must remain visible and cannot be represented by synthetic data.

## Deliverables and acceptance

Publish report Markdown/JSON; 23 section files; coverage for 150 aspects and
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

Parent-phase Docker workers use a single-stage Python 3.11 image without
`USER` instructions, allowing SDK skill-preparation hooks to add native tools.
OpenCode and sandbox system setup belong to the separate OpenShell image.

### Immutable review handoff

The owner planner persists stable tasks, bounded prompts, evidence selections,
configuration, and SQLite reservations before dispatch. Pending reservations count
toward `max_calls`; ambiguous execution is never automatically refunded. Frozen
admission JSON is published with the runtime run ID through SDK artifact helpers.
Reviewers use isolated attempt workspaces and publish task-specific result files.
They have no writable budget database or owner catalog mirror. The next owner
planning pass reconciles only Core-committed result receipts, verifies citations
against the frozen owner snapshot, then publishes domain receipts idempotently.
This migration retains serial dependencies and does not introduce parallel review.

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
otherwise. The default hybrid encoder covers every byte using pooled pieces;
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
