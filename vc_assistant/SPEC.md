# VC Assistant SPEC

## What We Want To Achieve

Build a reviewable VC analysis workflow that monitors a folder containing one or more startup document packets, groups those documents by company, coordinates a reusable specialist-agent crew through explicit DAG steps, performs privacy-safe public research, runs deterministic numerical analysis for each valuation heuristic, audits the results, and writes organized score-only reports.

## Customer Problem

Early-stage startup review is noisy. Pitch decks, notes, founder bios, traction updates, market claims, and technical material arrive in mixed formats. VC analysts need a fast way to compare early opportunities with lightweight heuristics while preserving evidence and avoiding fake precision.

## Design Details

The blueprint is a scheduled batch-style OtterDesk workflow. Agents are reusable specialist workers; steps are durable phases in the workflow DAG. Step ids use action phrases, agent ids use role names, and the two namespaces must remain disjoint.

Each manifest step references a `payloads/steps` module through `run.definition`. That module declares the step's input contract, output contract, and internal `StepSpec` collaboration graph. `agents.registry` defines handlers and immutable handler parameters independently from optional `llm.agents` review configuration. An agent may be reused by multiple steps or calls; every compiled call receives a unique invocation id derived from its step and call alias.

The durable data plane is the run filesystem. The live message plane is acknowledged Redis Streams. Agent handlers use the route-free SDK `receive_input` and `send_output` functions. The workflow DAG contains only logical step dependencies; each compiled step contains a generated source boundary, its internal agent graph, and a generated sink boundary. The internal graph owns routing, fan-out, fan-in, retries, ACKs, deduplication, and dead-letter behavior. `prepare_company_evidence` runs extractor → normalizer, while research and scoring calls run in parallel and join before the sink completes the logical step.

The workflow requests `manual_recover`. Redis retains bounded live coordination state, but a lost runtime lease does not trigger repeated automatic reconstruction of the full 46-agent graph. The supported recovery path is to submit a fresh run against the same durable inputs and filesystem artifacts; completed artifact writes and invocation idempotency records make that rerun safe.

Within an invocation, research planning and collection reconcile their effect
intent against the Core-owned action ledger. Preparation may retry only when
that invocation's budget scope has no admitted action. Unknown model/browser
outcomes stay fenced; unrelated specialists' actions do not establish dispatch
for this invocation. Required knowledge retrieval retains its original failure.

Production code follows a strict ownership boundary. `payloads/steps` owns orchestration declarations, the SDK block worker owns execution, `payloads/domain` owns VC-specific evidence/research/valuation/report policy, and `payloads/runtime` owns runtime context and shared-service preparation. Domain-neutral message envelopes, artifact references, durable replay, document intake utilities, and control agents belong to the SDK, reusable agents, and skills. No aggregate `agents/domain.py` compatibility module is permitted.

Every scorer registry ID resolves to a distinct stock block binding and domain hook. The shared scorer executor handles durable queue mechanics, while deterministic formulas remain individually inspectable under `domain/valuation` (`first_chicago.py`, `berkus.py`, `scorecard.py`, and the other method modules).

| DAG step | Required agents |
| --- | --- |
| `detect_packet_changes` | `startup_folder_watcher` |
| `assemble_company_packets` | `company_packet_grouper` |
| `prepare_company_evidence` | `document_evidence_extractor`, `claim_normalizer` |
| `plan_public_research` | `research_planner` |
| `collect_public_research` | `company_identity_researcher`, `funding_researcher`, `market_comp_researcher`, `traction_verifier`, `rendered_page_researcher` |
| `reconcile_research_evidence` | `research_reconciler` |
| `calculate_valuation_scores` | `berkus_scorer`, `scorecard_bill_payne_scorer`, `risk_factor_summation_scorer`, `venture_capital_method_scorer`, `first_chicago_scorer`, `comparables_market_multiple_scorer`, `cost_to_duplicate_scorer` |
| `audit_valuation_analysis` | `score_consistency_auditor` |
| `write_company_reports` | `company_report_writer` |
| `publish_batch_summary` | `batch_index_writer` |

The workflow groups first-level input subfolders as companies. Loose files are grouped by inferred company names from filenames or document text. Public research is constrained to privacy-safe queries based on company names, product categories, domains, and public claims.

The online research layer uses `web_browser_skill` as its only browser capability. Standard mode performs provider discovery, readable plain-text extraction, bounded retries, throttling, and adaptive local engine selection; explicit deep mode renders JavaScript-heavy public sources such as Crunchbase through a deterministic, policy-governed `agent-browser` actuator. MirrorNeuron remains the planner. The browser layer owns session/domain policy, approval gates, per-run audit records, and bounded artifacts; it does not expose eval, arbitrary JavaScript, uploads, profiles, clipboard access, raw CDP, or agent-browser's autonomous chat loop. The workflow records source status, snippets, warnings, and blocked/login/robots outcomes rather than bypassing access controls. Changed company packets, per-company research agents, and numerical method scorers run with bounded parallel workers while outputs remain ordered by stable company slug.

Actor-style LLM analysis uses MirrorNeuron's logical `default` model. The
runtime automatically selects and prepares a compatible model on first use
for the available hardware. Supported Macs and low-spec PCs can use Gemma 4; the blueprint has no
Nemotron dependency, fixed parameter count or quantization, or dedicated-GPU
requirement. Concrete model compatibility belongs to the runtime catalog.
An operator-selected provider definition can replace the default without
changing the blueprint.
Numerical scoring remains deterministic: formulas, weights,
scenario math, missing-evidence status, and audit checks are owned by
deterministic workers. Non-substantive records such as research plans,
configured references, disabled browser fallback notices, unavailable skills,
blocked pages, and failed requests do not create comparable evidence by
themselves.

Local LLM calls are deliberately backpressured. The default run serializes Docker Model Runner calls, spaces them slightly, keeps company and research-agent defaults serial, and caps agentic research loops so a scheduled batch does not burst many model calls at once.

## Input

The blueprint requires no initial configuration: bundled synthetic startup
packets and a local output path provide complete first-run defaults.

The prototype accepts local startup documents in PDF, TXT, Markdown, JSON, and CSV formats. MarkItDown converts text, structured data, office files and embedded PDF text in `docs_to_markdown_skill`. Scanned PDFs and document images use its dedicated LLM OCR route. The skill owns its model and prepares it lazily only when OCR is required. If a PDF startup packet cannot produce usable text, the batch run fails closed instead of creating metadata-only evidence.

## Output: Expected Customer Outcome

Version 1.1.1 sets the default host output folder to
`~/Downloads/vc-assistant`, matching the declared job name. Previously
submitted jobs retain their configured destination.

Batch host delivery places run artifacts under `run_<timestamp>/` in that
destination. `outputs.job_files` declares `watch_state.json` and
`context_sources/` as job-level entries, retained at the root across runs.
The SDK/runtime owns folder allocation and result publication.

Each company gets a dedicated output folder with structured JSON, Markdown, source records, and local evidence records. The report covers:

- Berkus Method
- Scorecard / Bill Payne Method
- Risk Factor Summation Method
- Venture Capital Method
- First Chicago Method
- Comparables / Market Multiple Method
- Cost-to-Duplicate Method

If evidence is missing for a method, the method status is `insufficient_evidence`.

Internal artifacts include `company_work_queue.json`, company fact tables, research ledgers, method-score files, audit findings, research coverage, method coverage, and a run summary.

## Persistent job data

The stable job owns cross-run knowledge, DuckDB RAG data, and explicitly
durable state. Run inputs and reports remain execution-scoped. Seeds apply only
on job initialization/reset; run cancellation, retention, or deletion does not
remove shared data. All agents in a job use the same
`databases/rag/knowledge.duckdb` and collection namespace. The reusable SDK RAG package owns
a job-scoped Unix-socket service that retains the only DuckDB connection;
parallel agents submit indexing, state, and retrieval operations through that
service instead of opening the file independently.

## Evaluation Criteria

- Company grouping is explainable and stable.
- Workflow step ids and agent ids remain disjoint.
- Every step definition references one or more valid registry agents and declares its input and output mappings.
- Multi-agent research and scoring crews join before their containing step completes.
- Agent messages contain bounded results and artifact references rather than confidential documents or large ledgers.
- `payloads/runtime/runtime.py` remains below 500 lines and contains only runtime context, configuration, service preparation, observability, and lifecycle persistence.
- `payloads/agents/domain.py` does not exist, agent modules do not import it, and no VC domain module grows beyond the architecture size guard.
- Every valuation scorer registry entry resolves to a distinct block hook, manifest-owned method and individually owned formula module.
- All seven method sections are present for every company.
- Scores are included where evidence exists.
- Missing evidence is explicit and not hallucinated.
- Public research avoids confidential local excerpts.
- Public research attempts company website, Crunchbase/profile, founder public profile, funding mention, press, competitor, and market-context verification where configured.
- Changed company packets are processed concurrently when `execution.max_company_workers` permits, without changing output ordering.
- Each numerical method emits `status`, `score`, `inputs_used`, `formula_or_weighting`, `assumptions`, `source_refs`, and `warnings`.
- The score consistency auditor flags missing method outputs, invalid scored/null states, unsupported assumptions, and formula coverage gaps.
- Scorecard and Comparables remain `insufficient_evidence` when only default filler values or non-substantive source records exist.
- Outputs are organized into one subfolder per company.
- No investment decision label is emitted.

## Prototype Limits

This is an early heuristic report assistant. Scores are not valuations, investment recommendations, legal advice, or financial advice. Comparable, exit, and rebuild-cost outputs are deliberately conservative when source evidence is thin.

## Persistent Job response service

The top-level response service stays available without an active screening
batch. It combines sanitized role, schedule, safe configuration, lifecycle,
and latest-Run evidence with the existing Job-scoped startup research RAG. It
answers through `ask_job` without starting research, altering scoring, or
taking investment action.

## Upgrade Path To Real Customer Use

Add richer source citation capture, customer-specific scoring weights, authenticated market-data and funding-data connectors, analyst review annotations, historical calibration against partner decisions, and governance controls for confidential data handling.

## Block composition (5.0.0)

The four intake specialists use native block contexts and explicit upstream
checkpoints. Sources are captured as portable, hash-verified SDK file graphs;
conversion and normalization use captured bytes. Checkpoints bind the Job, run
and original settings. Prepared evidence freezes before optional actor review,
and a lost model response cannot trigger an automatic duplicate call. Actor
privacy, RAG citations, qualified runtime-memory records and conversion-failure
diagnostics remain. Original and processed source files remain reachable through
the artifact graph. Cache fingerprints use relative source identity and content;
older absolute-path fingerprints refresh once.

The research planner uses the same native snapshot authority. Its bounded entity
queue and privacy-safe research policy run behind a journaled planning request;
the complete response freezes before optional review. Unknown planning outcomes
cannot redispatch models or browser tools. SDK action reservations retain their
charges across interruption, including an unknown optional-review outcome.
Resource preparation takes native contexts and input ledgers directly.

Five public-research specialists and the reconciler use the native checkpoint
contract. Branches bind one exact planning reference and complete active-company
coverage. Reconciliation validates the declared branch set and merges findings,
qualifications and traces deterministically; source data stays in verified
artifact graphs. A completed phase checkpoint is invocation-owned and frozen
before inspection views, permitting retry without observing a newer global ledger.
Review context freezes before model dispatch. Its reference, authored-memory
witnesses and individual branch references stay reachable from the joined graph;
retry cannot silently substitute newer retrieval results after a known response.

Native workers reserve actions through Core's `mn.workflow_budget/v1` protocol.
The source policy resolves the configured allowance once. Core serializes admission
at the run owner, validates identity/scope, persists before granting work and
preserves charges across unknown outcomes and checkpoint recovery. Worker copies
cannot reset or raise that allowance. Audit records and byte quotas are bounded;
capacity errors never authorize work. Existing metadata privacy rules apply.

Seven valuation specialists consume the reconciler's frozen company fact tables
through native contexts. The auditor validates the exact seven branch roles,
common research checkpoint, company coverage, method IDs and original fact
tables before applying the existing deterministic audit/composition policy.
Formulas remain in their existing method modules. Each scorer's review recalls
its own method result first, including formula, input names, numerical details,
assumptions, references and missing-evidence qualifications. Prepared audit data
freezes before review; a known model response replays with the same checked time,
context and evidence. Branch reviews merge in manifest order, and their frozen
contexts and witnesses remain reachable through the scoring proof graph.

All 21 specialists now use native contexts. Report writers consume scoped audit
and company-publication checkpoints, with SDK immutable file publication and
receipts. Required company files, source subjects and watch state precede terminal
delivery. Batch review and final report data freeze before writes, preserving
known responses, health/elapsed values and byte identity across delivery retries.
Logical public names are relative. The SDK verifies files and receipts before
run/output-folder delivery; Core handles declared OpenShell exports when selected.
All selected reviews use the same Core-owned run allowance. Legacy runtime-context
and local-budget loaders are removed; workflow-state files are inspection views.
Domain formulas and StepSpec joins remain intact. Metadata traces preserve local
records plus upstream specialist-qualified observations; private initialization
diagnostics may be absent from the aggregate, explicitly qualified in coverage.
Company coverage timestamps come from the frozen report clock. Every company,
batch and source publication freezes its complete byte inventory through the SDK
before the first receipt. Completed source preparation is reused after interruption,
including a crash after receipts but before the enclosing phase checkpoint. Receipt
verification remains strict; retries do not replace changed or corrupt artifacts.
The matching SDK and re-prepared Job definitions are required for this behavior.
Main SDK requires dev27, blocks dev27, common dev25 and coordinated Core support.
Core keeps delivery and logical completion. Full catalog migration still includes
unfinished CCTV event hooks; no live provider/device qualification is claimed.

## Blueprint package format

This blueprint uses the canonical blueprint/v1 format in both folders and ZIPs.
`manifest.json` contains identity, semantic release version, and document references.
`workflow.json` owns logical topology and policies; `execution.json` owns workers,
resources, and services; `contracts.json` owns input/output and artifact contracts.
Platform descriptors live in `extensions/`, package requirements in
`dependencies.json` when present, and operator defaults in `config/default.json`.
The SDK reads these documents together and compiles the Core execution artifact.
A ZIP contains the same files as the folder. Local overrides and invocation
configuration are resolved by the SDK before launch.

## SDK capability dependencies

Release 1.1.0 migrates infrastructure from retired skill distributions to the
current SDK component contract. `dependencies.json` declares pinned
`mn-python-sdk-common`, `mn-python-sdk-rag`,
`mn-python-sdk-job-response`, and `mn-python-sdk-mcp` under `packages`.
Task capabilities remain under `skills`; reusable workers remain under `agents`.
The skill and agent pins follow the migration releases used by the OtterDesk
catalog (1.3.23 and 1.3.10 respectively).

Prompt/event helpers use `mn_sdk_common`; actor configuration and usage use the
actor-review agent; foundational LLM access uses `mn_sdk.llm`. RAG owns indexing,
retrieval, and the shared Job database, with the SDK runtime model adapter
injected for embedding preparation and retrieval. The RAG base dependency owns
DuckDB installation; the blueprint does not maintain a second dependency list.

Local development (`MN_USE_LOCAL_SKILLS=1`) resolves declared SDK packages from
`mn-python-sdk/packages` and skills/agents from their companion source projects,
ignoring release pins. Binary installation uses the pinned GAR releases.

The Markdown runtime profile (`text_memory.enabled=true`) commits complete
preprocessed, redacted document text through Membrane. Private input bodies are
restricted to input/company-analysis principals; actor-review retrieval sees only
privacy-approved observations. Actor context assembly uses CompileEvidence v2 and
saves full witnesses in workflow-state artifacts, outside model context. This
replaces the retired in-process WorkingMemory helper; learned compression remains
disabled. Source retrieval and final verified token admission remain distinct.

## Context engine contract

This release declares `mirrorneuron-python-sdk[context]` in `dependencies.json`. Worker preparation installs the Membrane v2 client (>=2.0,<3); local source mode stages its matching source project. `mn.context` declares the Markdown profile, and `text_memory.enabled=false` explicitly disables recall. The context service stores Markdown revisions with one disposable DuckDB per job and uses CPU only. Set `MN_CONTEXT_ADDR` and `MN_CONTEXT_AUTH_TOKEN` through trusted runtime settings. Optional `MN_CONTEXT_OBSERVABILITY=true` logs authorized source and context content. No model compressor, Redis memory, or automatic migration is required.


## Runtime memory and external knowledge composition

External knowledge remains in the job RAG index. A semantic query selects a small passage response with citations; Membrane composes that response ephemerally with source-qualified runtime query results and the current instruction. RAG passages are never copied into runtime memory, and the full knowledge corpus is never sent to the model. Runtime memory stores normalized claims, source qualification and method results created during this workflow, rather than actor prompt snapshots. Raw document excerpts remain restricted to their input consumers. Snapshot-scoped typed table queries select whole observations; source handles and retrieval witnesses stay in sidecars. Empty or completely omitted packets cannot claim readiness. Metadata compaction preserves runtime evidence, the selected RAG bodies, every selected citation and current state; its character target cannot silently remove evidence. The runtime model gateway remains responsible for complete-request token admission, including system instructions, schema and output allocation.

## Authored runtime records and separate original sources (1.2.1)

Runtime publication accepts validated `RuntimeRecord` Markdown, with typed scalar
Facts, complete Notes and company/claim/evidence/source Relations. Batch authoring
validates before semantic publication. Snapshot identity and a checkpointed actual
publication clock make retry idempotent. Known event timestamps normalize to UTC;
missing, naive or invalid event times stay unknown. Publication is not an inferred
event time. Source fetch `status` and extraction `retrieval_status` stay distinct.
Exact Facts are not duplicated in Notes; explicit nulls and complete non-scalar
values are preserved. Raw excerpts, RAG bodies and prompt snapshots are excluded.

Actor plans retrieve up to three known-time tool outcomes for that actor, one
explicit unknown-time outcome when capacity permits, and relevant claim/method
rows within the configured result limit. Source metadata is the fallback only
when no eligible claim/method exists. Every selected row hydrates the whole current
authored revision with complete citation bounds. Incomplete or all-omitted packets
retain explicit failure status. Bounded recall is not proof of exhaustive coverage.

Each actor query supplies the exact published snapshot's source IDs. Snapshot
filters and source scope jointly constrain retrieval and canonical verification;
earlier and concurrent review snapshots do not expand the verification population.

Original UTF-8 inputs use `source_text_query` and a distinct physical Job corpus.
Intake receipts bind source identity, original hash and revision; company analysis
queries only that authorized pinned input. Failed pin validation never falls back
to a preview. Inputs without source query enabled retain their preview contract.
Source search precedes the existing bounded deterministic extractor and may
include neighboring source text; it does not guarantee exhaustive extraction.
The default actor recall allowance is 32,768 bytes with six selected results;
8,192 bytes is an explicit comparison control. Complete-request token admission
and external RAG composition retain their separate contracts.

### Source-confidence contract corrections

Keep search-result-page evidence and search-only claim confidence at or below 15;
graph propagation cannot lift this ceiling. Normalize typed polarity values when
binding Bayesian evidence. Founder/company sources may supply self-reported
support, but keywords mentioning invoices, contracts or usage cannot establish
independent observations. Search results and failed/blocked sources establish no
Bayesian verification observation. These are heuristic belief updates; published
qualifications must retain the lack of independent support.

## Shared capability ownership

Selected PDF batch extraction and usable-text checks use the shared `docs_to_markdown_skill`. It also owns the reusable intake helpers; the retired document-reading package is no longer a dependency. Company grouping policy, synthetic test evidence, redaction policy, valuation and evidence interpretation remain blueprint-owned.

## Unified document conversion and artifact source intelligence

VC intake calls `mirrorneuron-docs-to-markdown-skill` for every supported source.
PDF/OCR, text, JSON, CSV and office/spreadsheet conversion share one skill API.
Complete processed/redacted Markdown files are saved under the SDK-provided
shared job output path at `context_sources/inputs/`, retaining the original relative
filename with `.md` appended. Input and Markdown hashes, conversion method and
pinned source revisions accompany the files. The output writer publishes its
supported artifacts the same way under `context_sources/outputs/`.

Syncthing replicates these files and `inputs.json`/`outputs.json` source catalogs
with the other shared submission artifacts. Membrane SourceCorpus indexes their
Markdown as the operation subject, with MarkdownDocumentAdapter for navigation.
Artifact source intelligence uses `source_context.enabled` independently of
runtime recall and performs no runtime-session journal reads. Runtime memory
contains authored workflow observations, claims and method outcomes. Raw file
bodies and output artifacts stay in the separate source corpus. Public research
retains its redaction and confidential-source boundaries.

The stable shared job output folder owns `context_sources/`, reused across
workflow runs. Conversion receipts validate original and Markdown hashes and
converter/redaction policy. Unchanged files skip conversion and OCR; changed or
invalid cached files are converted again. Syncthing carries receipts and Markdown
alongside the other job artifacts. Membrane receives only processed Markdown.

## Standard MCP supervision

This package requires `mn.mcp.supervision.v1`. The SDK implements the shared manual, capabilities, context, results, activity, lifecycle, and operation tools. `knowledge/user_manual.md` is bundled with the prepared Job. Domain tools and their native JSON input/output schemas are declared once in `extensions/mcp.json`; response agents derive their bindings from it. All tool results use `mn.mcp.tool_result.v1`. Mutations require a request ID, and asynchronous work is observed through `get_operation_status`. Upgrade the installed SDK/API/desktop together and update idle Job definitions before using this contract.


## Stage-aware conversation

OtterDesk reads `payloads/prompts/conversation.json` as optional app-owned guidance. It combines this role and stage policy with the pending question, confirmed non-secret setup answers, recent dialogue, selected report and fresh Job state. Short follow-ups retain their topic; a correction does not silently change saved configuration.

Use Memory or explicitly ask to remember, edit or forget an explanation preference. This affects Chat wording only; working rules and evidence keep their existing domain controls. The optional `inputs.payload.supervisor_instructions` array is app-managed, never a required setup answer or a new workflow permission.

Use the matching company and run evidence through existing Job retrieval. Keep public claims separate from confidential documents, model estimates and older company facts. Scores are screening aids, not valuations or investment recommendations. No investment, founder contact or external transaction. Saved wording preferences cannot change scoring policy, factual evidence or research permissions. Existing submitted runs retain their configuration, evidence and approvals. An idle prepared Job may refresh through the existing conditional API without rehiring, resetting memory or mutating an active run.
