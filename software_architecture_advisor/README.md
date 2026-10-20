# Architecture Advisor

Local runtime models require at least one GPU with 49,152 MB of GPU memory.
When the selected review model is a registered remote API provider (including
a provider imported from JSON and selected as the runtime default), the host
requires any GPU and at least 16 GB of system RAM, with no GPU-memory, vendor
or driver constraint. Other hardware requirements still apply. Catalog listing,
validation and scheduling use the resolved requirements.

Every captured code file now has a persistent UUIDv5 entity identity independent
of its content and derived graphs. `File` nodes retain `node_id`, `repository_id`,
`current_path`, SHA-256 `content_hash`, `previous_paths` and language. Modules link
through `DECLARED_IN`; existing module/symbol and immutable citation IDs remain
compatible. Initial IDs use a canonical Git origin or optional
`ingest.repository_id`. For local repositories without either, a path-free
workspace ID is retained in each snapshot's `file-identities.json`. Keep this
registry when copying an index or changing checkout locations. Git rename
observations take priority; unique exact-content moves are conservative matches.
Ambiguous moves receive new IDs. Legacy snapshots remain readable; capture a new
snapshot to adopt file nodes. Pre-upgrade rename history cannot be reconstructed.

Runtime recall is selected by task: aspect analysis and challenges may use prior
navigation; file scans, evidence lookups, and section/executive summaries use
their explicit source and result packets. A globally enabled memory service does
not cause recall on every model call.

Architecture Advisor starts with offline static analysis, then asks the runtime
model to interpret focused architecture questions. The default review covers
six selected aspects with independent challenges and synthesis (19 baseline tasks),
rather than sending every source packet and all 150 aspects to the model.
All 150 aspects retain explicit coverage; unselected topics remain not analyzed.

Version 5 uses the SDK's `mn.blocks.bounded_investigation@1` composition for the
investigation initializer and planner. `extensions/blocks.json` declares its
domain hooks; Core still schedules the child rounds and OpenShell reviewers.
The advisor retains its task selection, frozen evidence, SQLite reservations,
call/deadline budgets and report policy. Block completion carries hashed catalog
references, verified again before the existing report publisher runs. This path
requires SDK/common/blocks `>=1.3.61.dev25,<2`. Its offline integration test covers
real task admission, source/result handoffs, replay, deadline termination and
report/dashboard publication with a synthetic model. Earlier live checks below
predate this migration; the new path still requires live qualification.

Open **Component and function evolution map** from the dashboard or report to
inspect file components, dependency cycles, direct callers/callees, source spans,
function version changes, call-name changes and functions that changed together.
Start with highly connected or frequently changed functions, inspect their
neighbors and evidence, then use the model report to decide what to review next.

## Run

Run the default xv6 repository review:

```bash
mn blueprint run ./software_architecture_advisor
```

To review a local repository instead:

```bash
mn blueprint run ./software_architecture_advisor \
  --set inputs.payload.repository_url= \
  --set inputs.payload.input_folder=/absolute/path/to/repository
```

The default URL is `https://github.com/mit-pdos/xv6-riscv`. Supply exactly one
source: a public HTTPS GitHub repository root or a local folder. The platform
stages local input; reviewed source is never imported or executed. Capture
includes code only: Markdown, other documents, JSON/YAML/TOML data, and sample
data files are ignored. Documentation, examples, samples, fixtures, dependencies
and build directories are excluded by `ingest.exclude`; this includes Elixir
`deps` and `_build`. `mix.exs`, `config/*.exs` and ordinary test code are included.
Only captured code enters source packets, retrieval and model review. Public Git
clones retain the existing bounded, credential-free acquisition policy.

Default review model: **Runtime default** (`mn/default`). OpenCode remains the
reviewer inside OpenShell. The SDK selects and prepares the runtime model, and
all review requests go through its LiteLLM gateway. Use `mn/<catalog-id>` for a
specific runtime model. An OpenCode provider/model choice must already be
registered in the runtime catalog; unavailable routes fail before dispatch.
SDK `>=1.3.58.dev65` is required for bounded durable bundle submission; install
the matching Core update for owner-forwarded creation and replacement.
There is no direct-provider or paid-model fallback. OpenCode public sharing,
edits, shell execution, delegation and web tools are disabled for review.

The existing runtime default currently selects Nemotron 3.5 Super VL.
Keep `opencode.model=mn/default` to use that override; this blueprint does not
register models or change runtime settings.

The platform prepares `mirror-neuron/software-architecture-advisor:local` from
`payloads/docker_worker/Dockerfile` using the standard Python 3.12 base with
the declared SDK, agent and skill packages. This single-stage Dockerfile has no
`USER` instruction, as required by the SDK skill-preparation hook contract. The OpenShell reviewer builds its own declared context at
`payloads/openshell_worker/Dockerfile` before sandbox creation. It includes
OpenCode 1.18.33, an explicitly selected Python 3.12 virtual environment and
`iproute2` for network isolation; the platform
installs declared packages into that image. An existing Docker-worker image
tag is not used for sandbox provisioning. The execution host needs Docker and a working OpenShell gateway.
Do not launch the packet worker natively; live calls verify the OpenShell runtime.
The sandbox policy allows only OpenCode's chat-completions requests to the
Mini and Spark LiteLLM gateways. Deployments using other gateway hosts must
set `opencode.gateway_hosts` to authorize those exact endpoints. SDK and CLI
render the policy's configuration bindings before provisioning and staging.

## Choose the model

The setup form offers Runtime default, Muse Spark 1.3 FreeOpenCode Zen and
Muse Glimmer 30BLocal Spark. The Muse choices require registered runtime routes;
upstream endpoint and credential configuration belongs to the runtime catalog.
Their existing display labels normalize to the corresponding provider/model IDs.
For example:

```bash
mn blueprint run ./software_architecture_advisor \
  --set opencode.model=mn/default \
  --set inputs.payload.repository_url= \
  --set inputs.payload.input_folder=/absolute/path/to/repository
```

Model selection and the SDK-prepared gateway route are frozen before review
admission. No provider credentials are copied into frozen inputs or output
artifacts. The old direct `opencode.spark_base_url` setting is rejected; register
the upstream route in the runtime catalog instead. Start a new run after changing
model configuration. OpenCode step receipts supply numeric cached-input and
reasoning-output usage to the owner run's SDK ledger. Reconciliation retains
stable call IDs, so interruption and replay do not count usage twice. Missing
provider receipts remain unmeasured. No extra tokenization requests are made.

## Workflow

1. Capture immutable source text, hashes and Git revision.
2. Run the reusable static-code-analysis skill once over the captured inventory;
   publish file components, call candidates, graph metrics and bounded function
   evolution. Feed supported mainstream-language syntax facts into the existing graph views.
3. Review six focused aspects, challenge them independently, follow up concrete
   gaps, synthesize the selected sections and write the executive review.
4. Validate exact evidence and publish the report, code map and audit registers.

Tasks within a phase have independent immutable handoffs and no artificial
serial dependency. The default round admits at most two tasks. Focused mode
challenges a completed analysis wave before admitting another analysis wave. Core owns execution and scheduling.
When static cycles exist, focused review starts with that measured signal.
Application functions with cross-file candidates seed the graph before query
planning; test-specific questions favor tests. Source selection prefers distinct
files, so similarly named tests cannot crowd out the application graph.

Defaults: `catalog_review.profile=focused`, 64 tasks, 32 model attempts,
20 rounds, two tasks per round, two evidence follow-ups (maximum depth two)
and a one-hour review allowance. This is a ceiling, not a promised completion
time. Two consecutive provider failures stop further model spending and publish
explicit partial model coverage with the static evidence. Other exhausted
budgets also retain their terminal reason.
Prompts remain at most 60,000 UTF-8 bytes; calls retain a 600-second deadline.

For an exhaustive catalog review, explicitly select its larger scope and budgets:

```bash
mn blueprint run ./software_architecture_advisor \
  --set catalog_review.profile=full_catalog \
  --set catalog_review.max_tasks=1024 \
  --set catalog_review.max_calls=1024 \
  --set catalog_review.tasks_per_round=32 \
  --set catalog_review.max_rounds=20 \
  --set catalog_review.walltime_seconds=604800 \
  --set catalog_review.max_followups=64
```

Full catalog mode retains source scans, all 150 analyses and challenges,
23 section syntheses and an executive review. It can take hours. The parent
workflow retains a seven-day upper bound for explicitly requested full reviews.

Configuration is in `catalog_review` and `opencode`. Existing capture limits are
5,000 files, 500 KB/file and 20 MB aggregate; tune `ingest` for larger repositories.
Unsupported extensions, symlinks, excluded directories and oversized/non-UTF-8
files retain capture limitations. Polyglot code reviews do not require Python
modules. The declared BEAM analysis skill installs pinned,
offline syntax parsers for Elixir/Erlang module declarations and dependency
candidates, alongside Python import extraction. Elixir lexical aliases, grouped
aliases, import/require/use/behaviour and module references, plus Erlang
behaviour/import/remote references, produce exact source-linked edges. Unresolved
references and syntax failures remain visible. C/C++, Python, JavaScript/TypeScript (including Node ESM/CommonJS), Rust, Go,
Java, C#, Ruby, PHP, Kotlin and Swift named functions and conservative calls use
the static-code skill. Local module-path candidates are extracted for Python,
JS/TS, Rust, Ruby and PHP; Go/Java/C#/Kotlin/Swift cross-file linking remains
unassessed without compiler/build evidence. Types, state and control/data flow remain Python-only;
BEAM still supplies module dependencies only. Macros, generated code, preprocessing,
dynamic dispatch, process messaging and supervision topology are not verified.
Optional graph exports must cite captured code; ignored documents cannot supply
source evidence. Metadata-only deployment/ownership collectors need explicit
code-linked exports when their source files are outside the code-only capture.

`offline=true` requests a static-only capture. The planner skips model-task
dispatch entirely, retains all unassessed tasks and publishes `not_analyzed`
coverage. It makes no OpenCode calls or synthetic findings. Model failures or malformed citations become blocked
task records. Attempt reservations prevent automatic re-execution after an
interruption; use a new run for an explicitly chosen retry.

## Results

The configured output folder defaults to `~/Downloads/software_architecture_advisor`.
`data/` and `web/` are Job-level entries: each run adds an immutable snapshot
and refreshes the latest dashboard. They are delivered by the SDK at the folder
root, rather than inside `run_<timestamp>/`.

```text
software_architecture_advisor/
  data/                         # JSON only
    report.json / coverage.json / evidence.json / claims.json
    static-code.json / function-evolution.json / architecture-score.json
    index.json / growth.json / workspace.json
    snapshots/<publication-id>/  # Immutable JSON for each captured review
  reports/                      # Markdown only
    report.md / code-map.md / architecture-score.md / improvement_prompts.md
    sections/ / work_packages/ / snapshots/<publication-id>/
  web/                          # Reusable rendering shells, JS, CSS and D3 license
    index.html / code-map.html / review-register.html / assets/
    snapshots/<publication-id>.html / maps/<publication-id>.html / reviews/<publication-id>.html
  run_<timestamp>/              # SDK run audit and original capture
```

Use the desktop’s co-worker web view or serve the result folder over HTTP.
For a double-clicked HTML file, select the requested JSON files in the offline
loader. This keeps HTML, Markdown and data separate; no CDN is used. The dashboard reads a projection of actual captured
source and validated review registers; it does not contain Atlas Commerce or
synthetic observations. JSON is authoritative; rendering shells contain no repository or review payload.
Local-file browsing uses explicit file selection. Web rendering
is a required final deliverable; a rendering failure reports failure after
preserving the already-written data and Markdown.

Views cover decisions, findings, bounded file/function dependency maps,
component/source details, exact dependency matrices and source sites, cyclic
module groups, structural hotspots, Git co-change with exact commit drill-through,
previous-snapshot source-hash changes and bounded reverse dependency paths,
proposed validation, evidence gaps, review drafts and engineering work packages.
Findings link supporting and contrary source excerpts, confidence, assessment,
human review and resolution separately. New reviews request an explicit question,
capability, trigger/mechanism, consequence, priority rationale, next decision and
closure condition. Earlier records without that detail remain visibly incomplete.

### From evidence to a useful change

The overview leads with one grounded next step, its proposed benefit and what
would count as a useful result. Work product provides copyable **Investigate**,
**Plan**, **Implement** and **Verify** prompts for a coding tool. Each prompt
retains the exact proposal or question, source/hash locators, counterevidence,
scope, alternatives, acceptance conditions and an honest completion report.
Implementation prompts require a source-supported, scoped work package; unresolved
premises lead to investigation/planning and verification instead. A cycle gets
an investigation prompt, not an automatic recommendation to split code.

The same prompt text appears in the main `report.md`/`report.json`, a standalone
`improvement_prompts.md`/`improvement_prompts.json`, work-package Markdown, the
dashboard and exported briefings. Prompt documents also accumulate inside
`reports/snapshots/<publication-id>/`. Copy prompt uses the clipboard; when unavailable,
the page selects the complete text for manual copying. Copying never executes
the prompt or changes source. Proposed benefits are not measured savings.

Handoffs are limited to 256 per publication. Prompt context keeps whole evidence
records within a bounded allowance; omissions and the exact retained JSON artifact
are disclosed. Oversized or incomplete contexts cannot produce implementation
handoffs. Search, prompt-type and component filters help locate relevant actions;
exports preserve all matching generated prompts.

The model produces the selected review; the Markdown report retains explicit
coverage across the 150-aspect/23-section catalog.
`report.md`, `report.json`, `review_index.json`, all linked registers and the
confidential `catalog/` task audit also remain per-run outputs. SQLite budget
ledgers are not exported as work product. Source originals stay in the restricted
run audit; the web export includes exact cited excerpts, not all unrelated code.

### Repeated reviews and saved decisions

Persistent state uses the declared `architecture_results` resource under the
SDK-provided Job data directory, isolated by stable Job identity. Publication is
locked and atomic. Earlier JSON snapshots and pages are retained; replay cannot
append a duplicate snapshot or roll the latest pointer backward. A run without a
Job data directory says `Single run; Job history unavailable`.

Snapshots compare only the same repository identity. Public Git origins provide
stable identity. For a local source without a canonical origin, explicitly set
`ingest.repository_id` to the same path-free logical name on each run; otherwise
cross-run repository matching is unavailable. Comparisons use the previous saved
Job snapshot, not an assumed PR parent or merge base. Scope and analysis setting
changes are disclosed. A finding missing from a later review is **no longer
evaluated**, rather than automatically resolved. Changed evidence requires
reassessment; wording/path changes can require manual continuity reconciliation.

Save view preserves the snapshot route, query, component filter and tab in this
browser. Review drafts require a named reviewer and rationale and remain bound
to the exact material digest. Export review decisions and supply the file on a
later run to persist them in Job history:

```bash
mn blueprint run ./software_architecture_advisor \
  --set inputs.payload.repository_url= \
  --set inputs.payload.input_folder=/absolute/path/to/repository \
  --set inputs.payload.review_file=/absolute/path/to/architecture-reviews.json
```

Review acceptance changes analysis state only. It does not modify source or mark
remediation verified. Briefings and work-package Markdown retain evidence locators,
qualifications and tests-not-run status.

### Evidence boundaries

Python/BEAM extraction and the shared 13-language syntax analyzer power the
structural map at their declared capability levels. Unsupported formats retain
source-text review and an explicit structural gap. The result page shows files
and functions; source paths do not establish logical components or deployed services. Static reachability is dependency context, not a reproduced failure.
Git history is anchored, limited to a first-parent window and supported current/historical source paths;
no rename tracking, PR normalization or automatic mechanical-change classification
is asserted. The two directional co-change rates and union overlap expose their
different denominators and exact commit sets.

This version does not implement multi-repository bundles, semantic contract
compatibility, authoritative runtime/test-result imports, approved rule/exception
evaluation, deployment/state/workflow reconstruction, performance/capacity models,
or web natural-language answers. Those require further typed evidence collectors
and integrations; the dashboard shows the missing evidence instead of invented
results. The existing Job conversation service remains available through OtterDesk.

Version 3.8.2 publishes the finished `report.md` and its explicitly published
section Markdown through the document-conversion skill into run-keyed
`context_sources/outputs/` at the Job output root. Original and converted hashes
remain in conversion receipts; retries reuse unchanged files and later reviews
retain earlier sources. The responder queries those complete reports through
Membrane source intelligence. Captured code, unpublished drafts, task audits and
budget ledgers are excluded. This requires SDK >=1.3.58.dev86; report queries
never start a review or authorize proposed implementation work.

The full report specification library is bundled at `payloads/report_specs` with
its manifest and hashes. Empty findings or proposals do not establish health.
All proposed work remains subject to separately authorized implementation scope.

## Validation status

The 3.7 advisor/manifest suite passed 125 tests, with 34 Linux-dependent skips.
The real-source dashboard and responsive browser checks passed. The full catalog
gate remains unclean. On 2026-10-17, remote Nemotron inference and the first
Core-committed OpenShell source review were verified on mini; the full 744-task
report and dashboard publication are still in progress. Production deployment
has not been verified. The
2026-09-28 live OpenShell check reached OpenCode Zen but the default free model
returned HTTP 403. That run produced an explicitly blocked/partial report; it
was not a completed architecture assessment. No alternative model was selected.
See [validation details](VALIDATION.md) for tested scope and remaining gates.

The review worker uses `mn.artifact_handoff/v1`. Planning freezes each prompt and
reserves its task's model budget on the owner before dispatch. OpenShell receives
only immutable admission inputs; it never receives the writable SQLite ledger.
After Core commits a task's result, the owner verifies it against frozen evidence
and writes the domain receipt. Missing or ambiguous results retain their budget
reservation and block automatic task replay. Serial task ordering is preserved.

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

## Retry failed investigations

Use `mn run retry <run-id> --dry-run` to verify that the failed investigation still
has a compatible checkpoint and retained evidence. Restore an unavailable resource
and retry with the same settings, or explicitly increase a declared allowance:

```bash
mn run retry <run-id> --set catalog_review.walltime_seconds=3600
```

`extensions/domain.json` declares adjustable review/investigation wall-time,
model-call and per-call timeout limits. The retry preserves consumed active time:
20 minutes consumed under a revised 60-minute allowance leaves 40 minutes.
Effective settings are layered over original configuration and frozen requests;
source snapshots, evidence and completed model receipts are not rewritten.
Committed source capture is verified and reused; uncertain model requests or
OpenShell effects block replay unless a durable verified receipt permits it.
Changed source inputs, topology or result-defining settings require a new run.
Historical investigations without sufficient retained state cannot be retried.

## Context engine contract

This release declares `mirrorneuron-python-sdk[context]` in `dependencies.json`. Worker preparation requires the Membrane v2 client (>=2.1.0,<3); local source mode stages its matching source project. `mn.context` declares the Markdown profile, and `text_memory.enabled=false` explicitly disables recall. The context service stores Markdown revisions with one disposable DuckDB per job and uses CPU only. Set `MN_CONTEXT_ADDR` and `MN_CONTEXT_AUTH_TOKEN` through trusted runtime settings. Optional `MN_CONTEXT_OBSERVABILITY=true` logs authorized source and context content. No model compressor, Redis memory, or automatic migration is required.

Historical runtime recall uses native filesystem passages with exact supporting
handles, bounded separately from the current task and source evidence. Structural
graph queries continue through the source-backed allowlisted views; each query
and canonical witness is retained in the catalog audit. Runtime notes cannot
replace a graph query or establish source claims.

Focused context selection now uses the existing call/state/test cross-layer
views for retry and idempotency questions, alongside typed path traversal.
Relevant views are selected deterministically under the existing query allowance.
The packet records its selection policy and omitted rows. Every displayed graph
row binds to supplied S- source spans; when its whole witnesses cannot fit, the
row is omitted too. Static calls and test presence remain distinct from runtime
measurements and executed tests. No parser or extra model call is added.

Each claim declares counterevidence coverage. Supplied counterexamples must cite
exact visible S- spans and remain linked in the final report. Unknown and bounded
searches with no result remain separate statuses.

Version 3.4.1 separates complete repository originals from runtime review
knowledge in Membrane's Context Intelligent System. The declared optional
`mn-context-source-code` adapter retrieves complete Python definitions and imports
at pinned source revisions. Syntax-unavailable files retain their originals and
an explicit native-text limitation. `catalog/source-inputs.json` and
`catalog/source-context/` preserve original-source bindings and query receipts;
cached source evidence is reauthorized and revision-checked before replay.

Validated review outcomes become authored Markdown Facts/Notes records. Claims,
qualifications and source locators remain complete; original citation excerpt
bodies stay in the original-source corpus. Runtime recall uses a DuckDB recent
query filtered to the current snapshot and, when available, aspect. Complete
original witnesses and prior claims have prompt priority over historical
navigation. Omitted whole records are counted explicitly. Default retrieval is
six results and 32,768 UTF-8 bytes; paired 8,192-byte tests remain the control.
These byte bounds do not establish serving-token admission or answer quality.
An authored schema declaration establishes query fields before the first review;
its separate family excludes it from review recall. An empty history remains
`no_evidence`, never a fabricated review outcome.
Whole source witnesses use available full-prompt space after mandatory
instructions and schema; a fixed one-third share cannot discard a fitting
definition. Prompt admission operates on a copy of frozen retrieval packets.
The optional adapter is declared through `skills`, the existing reusable
capability package mechanism. It is not an SDK component/provider.

Prompt admission now uses Membrane SDK support components. A graph relationship,
its complete witnesses, and any prior claims sharing those witnesses enter or
leave together. Counterevidence citations are part of each prior claim's closure;
oversized prior results are omitted whole. Unrelated complete source candidates
remain optional. Graph-packet omissions no longer contribute unused witnesses.
The prompt reports support/capacity status and omitted counts; each frozen request
retains a `support_admission` receipt with group IDs, members and omission reasons.
Only identical span identities at the same source SHA-256 can reuse evidence;
conflicting citation bodies fail. This is a byte-budget assembly fix, not a
serving-token or answer-quality claim. Existing frozen requests replay unchanged.
# Query-derived source support

The Python 0.1.3 source adapter retains complete local static helpers, constants,
import declarations, guards and enclosing lexical definitions for named-symbol
queries. Support metadata is pinned to each original revision and compiled as
required evidence; unrelated functions stay outside the closure. Static source
support does not establish deployed execution or imported implementation behavior.
The v3 original-source publication binding rejects replay of a catalog/query
created under the earlier selection policy; a new reviewed publication is needed.

## Version 3.5 source selection and traversal

Source discovery uses Membrane SDK 2.1 whole-unit search. Exact Python symbols
take precedence; otherwise optional `source_search.mode=hybrid` uses the declared encoder
and native lexical/vector ranking. `lexical` is the explicit CPU-only profile.
Embeddings cover the complete unit through pooled pieces; selected originals
remain byte-exact. Every selected root carries its declared local dependencies
as one support component. Syntax-unavailable and non-Python inputs use complete
text units with explicit structural limitations.

Graph seeds come from exact module/file bindings and ranked original evidence.
The default limits are 12 module seeds, four hops, 128 nodes and 128 edges,
configured under `graph`. Incoming caller/dependent questions reverse direction.
There is no two-module shortlist, three-view cap, automatic cycle query, or
separate 3,500-byte graph truncation. Query budgets still apply. Each path keeps
its edge witnesses and endpoint declarations; hydration expands those witnesses
to complete definitions and local dependencies. Final prompt admission keeps
paths and their complete source support together. Missing entities, unresolved
static references and capacity omissions remain visible.

For manual validation, start a fresh catalog with matching source-built Membrane
SDK and graph skill packages. Inspect `catalog/source-context/`, `catalog/graph/`
and frozen requests' `support_admission` receipts. A cross-file call path should
contain ordered edges plus complete caller/callee source; an oversized support
component should be omitted whole or report insufficient capacity. File UUIDs
and the identity ledger remain independent of source revisions. History recall
remains limited to aspect analysis/challenge; source lookups and synthesis do
not acquire historical context. These changes carry no measured quality claim.


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


## D3 architecture views and growth monitoring

Open `web/index.html` for one result page with eleven focused tabs: **Overview**,
**Dependency graph**, **Dependency matrix**, **Call paths**, **Change impact**,
**Graph evolution**, **Changes together**, **Size and churn**, **Recommended
prompts**, **Architecture score**, and **Evidence coverage**. Each chart has its
own tab; there is no secondary chart switcher. Navigation stays in a quiet side
rail on desktop and a compact grid at narrow widths. Only file and function
relationships are shown; directory aggregation and directory ordering are removed.
Source paths remain visible for identification. The score's saved measurement
policy is unchanged and its directory-based proxies remain explicit in its method.
`web/code-map.html` opens the same page. The overview leads with a measured
investigation unless a supported, source-complete work package is available.
Unchallenged proposals stay visible as proposals. It shows structural weaknesses, compact evidence coverage and up to two copyable prompts.
Scoring and detailed coverage each have their own tab. In Graph evolution, the three
largest measured adjacent graph transitions open directly at the relevant
file/function level, changed entity and previous-state comparison. Paths with
parser gaps are excluded from those transition counts. Repository measures are secondary.
The D3 tabs include a dependency matrix (DSM), dependency neighborhood graph, size/churn
treemap, change impact, temporal coupling, and evidence-backed function call paths.
Graph evidence, chart records and interpretation notes are collapsed below the
chart; candidate blast radius is shown only in its own tab. The dependency graph
shows the bounded captured network, with connected, all-entity and two-hop
neighborhood scopes. The treemap is flat, containing files or functions without directory groups.
The views share file/function focus, relationship filters, exact witnesses and
committed states. Matrix ordering uses measured file cycles, coupling or names; without an
approved layer policy the report cannot classify a layer violation. The matrix
shows at most 80 entities and names its truncation. The treemap uses physical
source lines for area and changed commit counts for color; complexity, code
health and severity are not measured. The impact view traverses up to four hops
and 128 entities, drawing at most 32 with a complete reached-path table.

The **Graph evolution** tab puts the evolving network first. Play or scrub
committed states to see nodes and relationships appear and disappear; removed
items remain as baseline ghosts, changed function definitions are amber, and
parser gaps remain unknown. The default compares with the window baseline; any
retained commit or the previous state can be selected. One layout over the
whole committed union keeps positions fixed, with zoom retained during playback.
The network displays up to 10,000 entities and 50,000 relationships; omitted
counts are explicit and the selected entity is retained. Exact relationships and definition comparisons remain in keyboard
accessible tables. Growth counts and curves sit in a collapsed detail panel. Merge commits use first-parent diffs, unchanged files are
included, and deleted historical source paths follow the configured directory
exclusions. Frames deduplicate definitions and relationships instead of copying
source bodies. Historical parser gaps stay unknown and are excluded from
added/removed definition and call-pair counts.

### Switchable network layouts

The graph and evolution tabs share three locally implemented layouts, informed by
[Cambridge Intelligence's layout guide](https://cambridge-intelligence.com/learn/layouts/):

- **Organic (recommended default)**: deterministic multilevel matching followed by
  seeded D3 force refinement and Barnes–Hut repulsion. Use it for the overall
  connectivity pattern of an unfamiliar codebase.
- **Sequential**: strongly connected groups, dependency ranks and six barycenter
  crossing-reduction sweeps. Use it to follow direction through cyclic graphs.
- **Radial**: concentric levels of minimum undirected distance from the selected
  entity; other disconnected graphs use a most-connected root. Use it to inspect
  proximity to one file or function. Rings do not establish behavioral impact.

All layouts retain the same entities, relationships, selection and evidence.
They pack disconnected graphs separately and never introduce directory groups.
Organic spatial clusters are visual hints, not discovered architectural modules;
sequential ranks are not approved layers. Switching layout recalculates positions;
scrubbing commits preserves them within the selected layout/scope.

HTTP previews calculate layouts in a cancellable, 20-second-bounded Web Worker.
Only the existing bundled D3 library is used; no commercial SDK, CDN or server
layout service is required. Canvas avoids thousands of SVG/DOM elements, D3
quadtrees handle picking, and labels are revealed with zoom and deconflicted.
Use **Fit visible graph**, **Zoom to changes** (evolution), **Focus selected**, zoom/pan and the native file/function
selector. Arrow keys pan the focused chart, +/− zoom, Home fits and F focuses.
Exact relationship evidence stays in the expandable tables.

The default connected scope hides entities with no observed relationships while
retaining the selection; **All files** or **All functions** includes them. **Selected + 2 hops**
uses undirected adjacency to narrow dense graphs. Bounds retain at most 10,000
entities by degree (including the selection) and 50,000 relationships, favoring
selected-entity links when trimming; unknown relationships are never invented.
The UI discloses omitted counts. Search can select an entity beyond the displayed
subset. Offline file mode uses the identical bounded algorithm on the main thread
because file-origin workers are unavailable; serve the export over HTTP for large
interactive graphs. Layouts are cached for reuse and canceled when leaving the view.

The co-change heatmap counts joint changed commits with both per-entity
denominators and matching commit IDs. An explicit filter excludes commits
changing more than 20 supported files; this does not label them mechanical.
Co-change is correlation, not causation. Empty cells do not prove independence.

Rerun the same Job through the existing co-worker controls or schedule to
accumulate reviews. `data/growth.json` records the metrics, baseline, deltas and
scope/method comparability. The detailed register’s Evolution view links each retained
graph. Separate Jobs have separate histories. This is monitoring at capture
cadence; the blueprint does not start a filesystem watcher or alter runtime
scheduling. For larger repositories, tune the history window explicitly; bounded
or shallow history cannot establish original creation dates.

For an exported result folder:

```bash
python3 -m http.server 8847 --bind 127.0.0.1 --directory /absolute/path/to/results
```

Open `http://127.0.0.1:8847/web/code-map.html`. For offline file mode, choose
`static-code.json`, `function-evolution.json` and `report.json` together from the
same `data/snapshots/<publication-id>/` folder. Include `architecture-score.json`
to display the score; older exports without it remain readable. The advanced `web/review-register.html` preserves saved review drafts,
source excerpts and cross-run comparisons; it asks for `workspace.json` and
`index.json`. It remains available under **Evidence, methods and saved records**. Files stay in the browser; no remote upload
occurs. The renderer rejects mixed source snapshot identities.

Presentation references: [Qodo Software Map](https://www.qodo.ai/features/software-map/),
[PuppyGraph’s dynamic graph overview](https://www.puppygraph.com/blog/dynamic-graph),
[Nominal](https://nominal.io) for the restrained industrial presentation,
and [D3](https://d3js.org). D3 7.9.0 is bundled with its ISC license and pinned
bundle checksum in `workspace_assets/vendor/README.md`. No other visualization
library or remote asset is required.


History budget exhaustion preserves current source facts and publishes explicit
unavailable history with the exact bound that stopped it. It does not silently
shorten the window or report zero churn. Invalid/corrupt Git objects and invalid
configuration still fail. Reduce the requested history window for fact/blob/byte
limits; increase the time allowance only for deadline exhaustion.


Local development uses the unpublished sibling skill sources, including temporal
frames, without requiring a registry publication:

```bash
cd /Users/homer/Projects/otterdesk-blueprints
MN_USE_LOCAL_SKILLS=1 MN_WORKSPACE_ROOT=/Users/homer/Projects/mirror-neuron-set \
  mn blueprint run ./software_architecture_advisor \
  --set opencode.model=mn/default --web-ui --benchmark
```

`mn/default` retains the operator’s runtime model override. A completed selected
scope can be a review draft while other catalog topics remain explicitly outside
scope. Implementation still requires separately authorized work.

Hotspot files outside the measured history scope are grey and labeled history
unknown, rather than zero churn. Partially measured function counts
are lower bounds. Text-only files retain measured size without gaining
structural or temporal coverage.

For frequent graph-growth captures without a model assessment, use the existing
`--set offline=true` option. The report marks model work not analyzed; static
graphs and growth history still publish. The planner does not send unassessed
tasks through OpenShell. Public repositories still require Git network access
for capture.

### Other repositories and source formats

The source URL is configurable; xv6 is only the default example. For RedisRaft:

```bash
MN_USE_LOCAL_SKILLS=1 MN_WORKSPACE_ROOT=/Users/homer/Projects/mirror-neuron-set \
  mn blueprint run ./software_architecture_advisor \
  --set inputs.payload.repository_url=https://github.com/RedisLabs/redisraft \
  --set opencode.model=mn/default
```

Capture recognizes additional source formats including Clojure, Lua, Dart, R,
Julia, Haskell, OCaml, F#, Perl, Groovy, Zig, Nim, Elm and Verilog as text-only
inputs. They do not acquire structural support by being captured. For another
source suffix set `ingest.additional_extensions`, for example
`--set 'ingest.additional_extensions=[".dsl"]'`. Documents and data remain
excluded. The capture records its effective suffix catalog and uncaptured
suffix counts; changed capture scope invalidates direct growth comparisons.

The tool accepts bounded software repositories, with capability levels stated
for the actual input. It cannot guarantee complete semantic analysis of every
language, framework or build system. Unsupported/partially parsed files and
unbound calls remain unknown; missing Git history leaves temporal views
unavailable. A repository with no capturable code receives an explicit input
error. Adjust the documented file/byte/history
bounds deliberately for larger repositories. No reviewed code, build, test or
dependency installer is executed.

### Further analysis priorities

**Call paths** starts with the selected file’s most connected
function and shows callers and callees up to two hops each way, bounded to 32
functions. Each reached function has a candidate path and immutable source
witnesses. Selection stays linked with the matrix, graph and impact view.
These are syntax/name candidates, not data-flow slices or execution traces.

After reviewing the output against [Joern slicing](https://docs.joern.io/cpg-slicing/),
[CodeCharta](https://codecharta.com/docs/overview/introduction/), and
[dependency-cruiser rules](https://github.com/sverweij/dependency-cruiser/blob/main/doc/rules-reference.md),
the next useful additions are:

| Priority | Capability | Evidence required before presenting a result |
| --- | --- | --- |
| 1 | Program slices | Imported control/data-flow analysis and exact symbol/statement identities; call reachability alone is insufficient. |
| 2 | Inferred subsystem boundaries | A bounded, tested community analysis in the shared static-analysis skill; expose its method and compare clusters to directories as hypotheses. |
| 3 | Architecture conformance | User-approved boundary rules with rule IDs and source witnesses for each violation. Directory grouping does not define intent. |
| 4 | Runtime execution views | User-supplied traces/profiles, joined to the captured revision. Static extraction does not run repository code or fabricate timings. |

Ownership, clone maps, metric cities and semantic projections should follow when
their input metrics and validation are available. The current page uses physical
lines and changed commits, and does not substitute these for complexity, coverage,
semantic equivalence or team knowledge. These priorities are a roadmap, not
capabilities claimed by this version.

## Advisor score: our own 100-point model

`advisor-structural-v1` is a transparent diagnostic policy, not an ISO/SIG rating
or a calibrated commercial benchmark. It applies to any captured repository but
returns **not assessed** wherever the necessary evidence is missing. It does not
rate correctness, security, latency, reliability or business architecture from
syntax alone. The exact formulas and input metrics are exported in
`data/architecture-score.json` and `reports/architecture-score.md`.

| Dimension | Maximum | Formula / evidence |
| --- | ---: | --- |
| Modularity & cohesion | 25 | 15 × within-directory dependency fraction + 10 × normalized entropy of directory file counts. Both are proxies, not proven business cohesion. |
| Dependency health & cycles | 25 | 20 × noncyclic-file fraction + 5 × (1 − directed graph density). Candidate graph only. |
| Change isolation | 20 | 20 × fraction of eligible source-changing commits confined to one directory. At least 10 commits and two groups; >20-file commits excluded explicitly. |
| Data ownership | 15 | 15 × single-owner-conforming accesses / assessed datastore accesses, only with a complete source-backed inventory. |
| Architecture rule conformance | 15 | 15 × passing / evaluated dependency rules, only with approved rules and complete source-backed evaluation. |

Static dimensions need dependencies, more than one known file and at least 80%
fully parsed captured files; modularity also needs two directory groups. Empty
graphs, one folder, missing history and missing rules do not earn perfect marks.
Unknown dimensions retain their weight: earned points through earned+unassessed
points form the provisional range out of 100. This is not a statistical confidence
interval. The UI shows assessed weight and parse coverage beside the score.
A single total is emitted only when all dimensions have evidence. No letter grade
or production readiness verdict is inferred.

The default publisher has no datastore-ownership or approved-rule collector, so
those 30 points stay unassessed. The scoring API accepts caller-declared complete
passed/total measurements with captured source hashes/spans; conformance also
requires approved rule IDs. It validates provenance, not the truth of a declared
measurement. Compare only the same repository, scope, extractor and score model.
`syntax-3` changes the method identity so earlier extractor results do not appear
comparable by accident. The score uses no model calls and does not execute code.

## Gap to commercial products (reviewed 2026-10-18)

This output is an evidence-preserving architecture exploration prototype. The
completed xv6 review analyzed 1/15 topics and completed no supporting challenges;
it does not yet provide commercially reliable defect findings. Qodo’s published
[Software Map](https://www.qodo.ai/features/software-map/) and
[enterprise capabilities](https://www.qodo.ai/solutions/enterprise/) describe
cross-repository context, per-PR updates, review workflows and organization rules.
These are vendor descriptions; we have not independently benchmarked their accuracy.

| Gap | This blueprint today | Next validation required |
| --- | --- | --- |
| Reliable findings | Exact source witnesses and explicit partial outcomes; this model run had timeouts/provider/validation failures. | Repeatable held-out defect benchmarks; completed analysis/challenge passes; precision/recall and useful-finding acceptance. |
| Semantic depth | 13-language definitions and conservative syntax/path candidates at documented levels. | Compiler/SCIP bindings, build configuration, framework contracts, indirect dispatch and data-flow evidence per language. |
| Multi-repo architecture | Bounded captured repository, file/function relationships, Git graph playback and reverse reachability. | Versioned cross-repo/service contract extraction and consumer validation. |
| Continuous review | Repeated Job captures and existing runtime schedules. No PR webhook, IDE review or CI gate is added. | Idempotent PR/diff integration and measured update latency at representative repository sizes. |
| Governance | Local review evidence, scoped prompts, missing policy marked unknown. | Approved versioned boundary/rule sets, exceptions, owners and resolution/acceptance history. |
| Validated scoring | Own explainable provisional model with unassessed weights retained. | Expert-labeled calibration and sensitivity testing across representative languages and project styles; no universal grade claims. |

Priorities are reliable completed findings first, stronger language-specific
bindings second, and multi-repository/PR workflow integration after that. A visual
map or a numeric score cannot substitute for those capabilities. Runtime and
desktop integrations remain outside this change’s scope.

### Comparison context and selection evidence

Graph evolution defaults to **Since window start**. The visible comparison strip
shows baseline → selected revision, available author dates, and the baseline
selector. The first captured frame is **Window baseline**; a missing date stays
unavailable. Replay links for a specific transition select **Since previous
commit**. Other retained baselines show **Custom comparison**. Author dates do
not change first-parent replay order.

Previous/play/next, the scrubber, position, and commit remain above the graph in
a sticky replay strip. Organic remains the default; Sequential and Radial are
available. Layout coordinates come from the full historical union. Playback
preserves the camera; **Fit visible graph** and **Zoom to changes** explicitly
frame displayed comparison nodes. Change zoom is disabled when no comparable
changes are displayed.

A deterministic summary lists up to three changed files or functions, ordered
by changed incident relationship count, then full identity. It distinguishes
definition edits from topology changes and reports observed cycle participation
without assigning defects or severity. Relationships touching parser gaps and
cycle changes whose union cycle may cross a gap remain unknown.

Explicit selection opens a non-modal source inspector (side drawer on desktop,
bottom sheet at narrow widths). Escape or Close dismisses it and restores focus.
It retains baseline-only definitions, revision-bound before/after links,
relationship witnesses, parser limits, and a matching canonical saved
**Investigate** prompt when available. Equivalent evidence tables remain below
the graph. Search alone does not open the inspector.

One expandable coverage line separates latest captured-source totals, the
selected comparison inventory, eligibility for definitive comparisons,
scope-eligible and displayed files/functions, scope exclusions, display caps,
and parser-gap files. Evolution connectivity and two-hop scope are explicitly
historical: they use the captured union, even when only two states are displayed.
These are derived presentation changes; saved JSON/Markdown and their schemas
are unchanged. `comparison-presentation.js` is the shared pure presentation model
for summaries, counts, inspector rows, prompt matching, and framing.

### Calm report shell

The report now opens with one recommendation, a visible coverage cue, and one
compact saved-prompt row. Additional findings open evidence in the same side
panel; long source inventories and methods expand on demand. Four common views
remain visible, with the rest under **More views**. Graph settings are under
**Options** and secondary graph commands under **Graph actions**. Comparison
identity and playback remain visible.

The header has a report title and source identity, with no logo. All global
header actions, including Export report, live in the right-side **Actions**
dropdown. Snapshot/revision metadata is in **Report details**. The shell styles
and menu behavior are separate local assets. [REPORT_DESIGN.md](REPORT_DESIGN.md)
records the architecture adapter over the shared skill; the runtime remains unchanged.

The report now uses actual **shadcn/ui + Radix** components, the public UI stack
used by Vercel v0: Button, Dropdown Menu, Tooltip, Tabs, Collapsible, Popover,
non-modal Sheet, Input, Native Select and Textarea. Geist fonts, neutral colors
and Lucide icons keep the same quiet design. Vercel's private GeistCN package
is not used. Component code is bundled locally; opening an export requires no
React server, CDN, npm build or model call.

The three-dot Actions menu, X close button, graph settings, playback and prompt
controls preserve keyboard access and evidence behavior. Large native select
inventories and D3 Canvas/worker graphs remain efficient. See
[REPORT_DESIGN.md](REPORT_DESIGN.md) for the reusable composition and
[report_ui/README.md](report_ui/README.md) for Node-only authoring/build commands.

The reusable report shell now comes from `mn-web-report-skill` (distribution
`mirrorneuron-web-report-skill`). Architecture-specific D3 graphs and playback
remain in this blueprint; component sources, fonts and common interactions live
in `mn-skills/web_report_skill`.
