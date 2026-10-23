# Litigation Analyst

## Version 3.3.1: simpler matter review

The local workspace has eight primary views: **Overview**, **Findings**,
**Questions**, **Evidence**, **People & events**, **Timeline**, **Reports** and
**Review history**. Matter settings is a secondary link. Existing bookmarked
routes and saved views retain their original identities: comparisons belong to
Evidence, briefing preparation belongs to Reports, and changes/audit share
Review history. Questions includes proposed internal review work and evidence gaps.

Overview puts recorded facts before counts and shows compact correction notices.
Flagged drafts appear under Findings → Needs attention and remain ineligible for
briefing. Reports displays eligibility before offering briefing creation. Evidence
has an adjacent text/file-name search and collapses hashes/processing metadata.
Graph selection highlights connections while preserving the displayed graph;
the source inspector sits beside it on wide screens and below it on narrow ones.

**Export** groups Markdown, source appendix, review decisions and **Save copy**.
Local review or saved-view edits display a save reminder. A requested download
does not certify filesystem persistence: check the saved HTML before closing.
Reopening that saved copy restores its decisions and views without a pending-edit
reminder. No browser storage, inference, source scope or export approval rules changed.

## Version 3.3: counsel reading workspace

The optional local webpage now opens with source-bound transaction amounts,
available review work and visible quality flags. A **Reports** view renders the
counsel reading brief and exact source appendix with headings, tables, quotations,
source drill-throughs and Markdown downloads. Reports describe the full authorized
snapshot; analytical filters do not rewrite them. Raw HTML in Markdown stays inert.

**People & relationships → People & events** connects named email correspondents,
communication records, counsel-labelled financial records and transaction references.
Select a node to inspect its neighborhood and exact supporting passages. Names are
header labels on separate address identities, not verified people. Shared-source
links do not infer participation, causation or payment. Chronology includes the
financial records with their date/annotation basis; unknown dates remain unresolved.
The advanced source graph and its temporal path tools remain available separately.
The map projects up to 60 communication records, 20 addresses per header field and
60 financial records; the display shows at most 49 links and 60 nodes. Omitted
record counts are disclosed. Duplicate communication copies are source records,
not newly inferred occurrences.

The reading brief rechecks exact source bindings and existing explicit-absence
consistency rules. Conflicting model claims remain inspectable in quality review
but cannot enter the reading brief or reviewed briefing export. Internal approval
and ledger review are distinguished from proposed bank-side evidence work. These
limited checks do not establish narrative accuracy or attorney approval.

To review an older delivered run, create a **separate** supplemental copy:

```bash
python litigation_analyst/render_review.py /absolute/path/to/run \
  --output /absolute/path/to/new-reading-copy
```

Use the normal blueprint Python environment with its declared dependencies.
Open `index.html` in the new folder. The folder also contains
`counsel-review-brief.md`, `exact-source-passages.md` and `review-data.json`.
No model, network, collection or external publication is involved. The command
verifies citation/source hashes, refuses overlapping/existing destinations and
preserves the original run. It requires the run's existing authorized
`case/workspace.json`; it does not migrate or rerun analysis. Keep the frozen run
for its authoritative report, audit and any originals omitted from the workspace.

## Version 3.2.1: source-grounded initial planning

The planner now receives a bounded inventory and complete source examples from
the verified frozen corpus, even without a matter file or historical memory.
Examples retain exact offsets and hashes, exclude handling-restricted material,
and keep structural dependencies whole. Duplicate content does not fill the sample.
This is navigation for choosing searches, not exhaustive evidence review.

The initial model schema requires execution with at least one enquiry. When no
authorized readable source or complete source context fits, the blueprint records
an explicit incomplete result without asking the model to invent case terms.
Use a fresh run; prior failed runs retain their immutable requests and artifacts.

## Version 3.2: complete evidence and attorney issue briefs

New runs preserve numeric references and monetary values in source units. Assessors
receive complete short sources when they fit, together with source-verified
transaction facts. Reviewers run a separate case search, inspect contrary context
and reconcile each finding with the supplied transaction records. Explicit absence
conflicts and unresolved financial consistency checks withhold the affected finding;
these checks do not certify semantic accuracy or replace attorney review.

The main report leads with counsel questions, supported draft answers, contrary
information, transaction distinctions and decision-changing next records. Existing
ledgers/policies route to internal reread; potentially restricted requests route to
handling review. Neither is presented as a customer collection request.
`case/consistency_review.json` and workspace packet coverage disclose the checks
and sources actually admitted to dispatched model requests, independently of whether the AI accepted a finding. Complete evidence takes priority over repeated methodology: assessment/review prompts retrieve two attributed guidance items; planning retains five.

The default remains `~/Downloads/litigation-analyst`. Open `latest.html` there for
the latest successfully delivered report/workspace. Prior runs stay in UTC
`run_<timestamp>/` folders. Updated SDK/CLI delivery resolves Core's completed
physical run ID and keeps delivery receipts outside frozen analysis outputs.
Delivery failure is distinct from completed analysis; copying does not rerun it.

Blank input retains pinned EMC-2. Root README/license/citation files provide
attribution, not evidence. Attachment gaps, unextracted archives and duplicate
copies are disclosed in `case/source_inventory.json`; duplicates are not independent
corroboration. `sample_attribution.json` preserves the license and pinned revision.
Do not feed `examples/emc2_evaluation/expected.json` to a model. After a new EMC-2 run:

```bash
python litigation_analyst/evaluate_emc2.py /absolute/path/to/run
```

`case/performance.json` records stage timing and measured decision usage. Missing
reasoning, calibration and repair durations remain unknown. Compare two completed
budget experiments using `compare_runs.py BASELINE CANDIDATE --expected PATH`;
provider latency and output size do not establish answer accuracy. Keep output
reserves unchanged until a corrected factual baseline and attorney review support
shortening them. No speed or accuracy gain is claimed solely from these changes.


The default `review.profile=first_pass` performs one round (up to two enquiries),
uses observed structural relationships, and limits investigation decisions to six.
A separate harmless readiness decision checks the selected model before source
acquisition or case inference. It sends no case material, preserves the configured
provider, and records readiness in `case/model_preflight.json`. The current SDK can report
unsupported token counting as unknown without blocking model generation. Preflight uses
the selected model's configured request timeout (180 seconds in the primary profile).
An optional positive `model_preflight.timeout_seconds` can shorten that timeout;
omitting it or setting it to null inherits the model setting. SDK preparation and
transport/repair attempts can take longer than one request timeout. The receipt records
the effective timeout and distinguishes request timeouts from other readiness failures
without storing provider error text. Platform input staging occurs before this check.
No local-model fallback is used. Source integrity and known context limits still apply.

First-pass planning checks a 600-second allowance between rounds; it does not
interrupt in-flight work, cap total wall time, or promise a dollar cost. Provider
transport/repair attempts are separate from decision counts. `standard` permits up
to three rounds and sixteen investigation decisions, with configured relationship
extraction (up to 256 separate calls). Retrieval is ranked, not exhaustive. Every
report/workspace discloses the effective plan and unexamined counsel questions.

Optional `inputs.payload.matter_file` accepts the bounded JSON contract in
`payloads/domain/matter.schema.json`. It is staged and frozen as `case/matter.json`,
with its hash and reviewed exclusions bound to the source inventory. Supply the
intended decision, parties, transaction references and numbered counsel questions;
legal framework text is counsel direction, not verified applicable law. Explicit
exclusions require source ID, reviewer, ISO review time and reason; mailbox-container
exclusions propagate to contained messages. Conservative automatic handling flags
remain in force. A new scope/handling decision requires a new run.

Optional financial-event annotations require one unique exact quotation, recorded
signed amount, explicit currency, transaction reference, ledger group and stable
record ID. Classifications/grouping are counsel annotations. Decimal arithmetic
sums posting and reversal records separately from requests, approvals and recorded
net balances. Repeated record IDs do not double-count; conflicting annotations fail.
The appendix and Chronology view expose quotations, exact offsets and hashes.
Accounting net, bank settlement, damages, intent and liability remain distinct.
Dates not literally quoted remain annotations; timezones are unresolved.

The counsel issue matrix shows linked hypotheses, support, counterevidence, unknowns
and unexamined questions. Structured follow-up drafts specify the requested record,
why it affects a decision, closure test and suggested priority with cited basis.
Owners/internal targets come only from counsel's `gap_assignments`, matched by exact
question. No records are collected and no communications are sent. The reviewed
briefing export omits unreviewed counsel intake, work requests and financial exhibits.

Authoritative additions: `case/review_plan.json`, `case/handling.json`,
`case/financial_review.json` and `transaction_appendix.md`. They are written before
the optional preview; the four published Markdown reports remain available when UI
rendering fails. Human review remains required for substantive findings.

### Manual test on mini with a registered remote default

The Nemotron JSON is a model-registration file, not a CLI `--config` flag. Once its model is registered as default, use the normal default route. From the repository root:

```bash
mn blueprint run ./litigation_analyst --node mirror_neuron@10.0.4.27 \
  --set llm.model=default \
  --set inputs.payload.input_folder=./litigation_analyst/examples/approval_reversal_case/inputs \
  --set inputs.payload.matter_file=./litigation_analyst/examples/approval_reversal_case/matter.json \
  --set context_memory.policy.window_tokens=32768 \
  --set context_memory.policy.output_tokens=8192 \
  --set llm.context_size=32768
```

Use the UI's optional matter input for real case annotations. The synthetic example
is `examples/approval_reversal_case/matter.json`; its answer key `expected.json`
remains outside `inputs/` and must never be supplied as case evidence. This example
is not attorney-reviewed customer evidence or a legal conclusion.

After a completed run, check exact spans and typed known facts offline:

```bash
python litigation_analyst/evaluate.py /absolute/path/to/run \
  --expected litigation_analyst/examples/approval_reversal_case/expected.json
```

This command never calls a model. Without `--human-review review.json`, acceptance
stays `pending_attorney_review`. A human review must name `reviewer`, ISO
`reviewed_at`, and exact `snapshot_id`; `finding_reviews` must cover every finding
once with `finding_id`, boolean `supported`, `evidence_ids` and `rationale`.
`criteria` must cover every expected qualification, counterevidence and gap once,
with exact `criterion`, boolean `retained` and `rationale`; also record
`unsupported_material_allegations` as a count. This is self-attributed review,
not authenticated attorney approval. No keyword score stands in for accuracy.
Validate on a representative set of at least 25 genuinely attorney-reviewed matters
before customer accuracy or readiness claims; the synthetic fixture is only a
mechanical regression. Do not fabricate that acceptance evidence.


Local models require at least one GPU with 49,152 MB of memory. When the selected default LLM is a registered remote provider, admission requires any GPU and 16 GB RAM; local-model VRAM constraints are removed through the existing SDK resource profile.

Version 2.7.5 uses the published graph analysis skill `1.3.49` and temporal
graph skill `1.3.60` releases. Their runtime modules match the verified source,
so release-mode API setup can install both declared graph dependencies.

Version 2.7 makes `web/index.html` the primary local investigation output, backed
by `case/workspace.json`. Findings connect to exact supporting/contrary passages,
comparisons, an address/source relationship graph, email chronology, questions,
gaps and reviewed work product. `workspace_status.json` reports preview failures;
verified Markdown and audit outputs remain available.

The page uses local assets, no CDN and no network requests. It is an offline copy,
not an authenticated sharing service, and does not attest where the runtime model
executed. Original PDFs open beside normalized cited spans. Other originals are
downloadable with generated locators labeled; transcript page-line navigation,
workbook cell/formula views and media playback are not provided yet.

Review a finding with your name, disposition, preserved wording and rationale.
**Save investigation copy** retains the selected view, filters and self-attributed
review decisions in another HTML file with authorized derivatives; originals are
excluded. Keep the delivered run package for original verification.
**Export review decisions** writes `review-decisions.json`. Select this as the
optional **Previous review decisions** input on a later run of the same matter.
Reviews are analysis history, never source evidence or executable instructions.
Conflicting reviewers remain visible and block approved briefing use.

Core-owned Job `state` holds immutable snapshots through the temporal graph
skill's `EvidenceHistory`. Changed wording/support/counterevidence/gaps requires
reassessment; old approval never silently approves a new source basis. Direct
test contexts without Job storage disclose single-snapshot mode. Use one hired
co-worker per matter to keep runtime memory and identity scope isolated.

Membrane original-source intelligence remains the retrieval authority. Authored
finding/locator records add `SUPPORTED_BY`, `OPPOSED_BY`, `CITES` graph navigation.
Planner RAW → GRAPH → RAW recall remains historical navigation; assessors/reviewers
examine complete current source evidence. The temporal graph skill separately
validates strict order, unknown clocks, bounded witnesses and occurrence counts.
These facilities do not substitute for one another.

`workspace.authorized_source_ids` defaults to all case sources; an explicit list
restricts generated output. Restricted/flagged content and dependent conclusions
are removed before serialization. Mailbox originals are omitted if any member is
excluded. This projection is not OS-level access control. JSON and run audit files
remain confidential owner artifacts, not sanitized briefing copies.
`workspace.max_page_bytes` caps the optional page at 32 MiB.

**Create briefing** previews reviewed findings/source versions and requires an
authorized recipient. It preserves supporting/contrary excerpts and qualifications,
and excludes unreviewed findings, full source bodies, originals, unused graph data,
saved views and historical changes. A supporting-only filter blocks export.
Offline copies cannot be revoked after distribution.

Chronology currently covers top-level email Date headers, retaining raw offsets
and minute/second precision; unzoned/undated times stay unresolved. Observed
addresses are not merged people. Graph display is capped at 49 edges; temporal
paths are prepared for up to 16 address seeds (4 hops, 128 nodes, 49 edges, 256
witnesses). Other seeds can use the bound case temporal tool. Missing/conflicting
Message-ID values are unresolved and excluded from distinct-message counts;
duplicate source copies remain inspectable.

See [the implementation report](IMPLEMENTATION_REPORT.md) for output-spec coverage,
validation, deployment limits and unimplemented features with their reasons.

Physical document, EML and mailbox graph nodes use persistent file UUIDs separate
from raw-file SHA-256 versions and normalized citation hashes. The source inventory
freezes `node_id`, `repository_id`, `current_path`, `content_hash` and
`previous_paths`. The case-owned `file-identities/` ledger beside run directories
preserves renames across successive captures. Use `investigation.repository_id`
for a stable matter identifier shared across checkouts/jobs; otherwise identity
uses the trusted job ID, Git origin, or a persisted workspace ID. Keep the ledger
when moving or rebuilding indexes. Git rename observations or unique exact-byte
moves can preserve identity; ambiguous matches receive new IDs. Embedded mailbox
messages and exact citation IDs retain their existing versioned contracts.
Existing graphs are retained; a new source/index run adopts the new IDs.

Only the round planner recalls runtime memory. Assessors and independent reviewers
receive their explicit evidence/results and guidance without historical recall.
Validated outcomes may still be published for later planning; enabling the memory
service does not inject memory into every model call.

Litigation Analyst freezes a legal-document folder, validates its lexical document
index and observed graph, then investigates through **LLM-planned dynamic child
workflows**. Findings receive a separate evidence-grounding review before the
existing deterministic citation checks and report writer run. Outputs are drafts
for human review.

## Extended local-model run on Spark

Use the normal mini runtime connected to Spark; see the root AGENTS.md for the
operator-requested reinstall and node reconnection procedure.

```bash
mn blueprint run ./litigation_analyst --node mirror_neuron@10.0.4.26
mn blueprint run ./litigation_analyst --node mirror_neuron@10.0.4.26 \
  --set inputs.payload.input_folder=/absolute/path/on/mini/to/case
```

Omitting the folder or leaving it blank in the setup form downloads the pinned
public [EMC-2 synthetic sample](https://github.com/jur1st/EMC-2/). The sample
action starts a first-pass analysis with a neutral, source-cited investigation goal. Invalid
custom folders fail explicitly. The platform stages local inputs to the worker;
never replace the local path with a guessed Spark path. Inputs are frozen before
analysis, never executed or modified. Do not put outputs inside the input folder.

Models retain the configured `default` gateway route, including a registered
remote provider. The SDK keeps supported serving-token counts verified; unsupported counts remain
explicitly unknown. This does not waive known context or source-integrity limits. The blueprint
does not substitute a local model or change the model registry.
The graph-analysis skill copies its digest-pinned Linux engine from a public multi-architecture GAR image.
Local development requires the companion SDK, agents and skills repositories,
Docker; graph preparation needs no gcloud or Git credentials. Use
`MN_USE_LOCAL_SKILLS=1` with source installations. Preparation does not publish packages.

## Indexing time budget

Version 2.7.1 gives index building the same 99,999-second step deadline as
investigation. Hybrid indexing can make 256 sequential model requests, which
can exceed one hour on a busy model owner. The configured extraction-call, unit
and provider-request bounds remain the limits on individual work. Core checkpoint
retry retains validated run-local decisions after an interruption. Existing frozen
runs keep their accepted deadline.

Version 2.7.2 also lets each worker inherit its phase's deadline. An explicit
one-hour worker override no longer cuts index building short; child tasks keep
their own 600-second limits. SDK dev52 or later accounts for structured model
decisions, including invalid provider responses, in the numeric run ledger.
Validated replay adds no model request or duplicate token measurement.

## Investigation rounds

The four parent phases remain source preparation → index building → investigation
→ reviewed draft publication. Investigation initializes a Core-managed child workflow:

1. The LLM planner chooses up to two falsifiable enquiries, distinct support and
   counter-evidence searches, and zero to two admitted read-only graph views per enquiry.
2. Core commits the round. An evidence collector executes each enquiry's bounded
   searches and graph queries, preserving exact source spans and audit records.
3. An assessor proposes a structured hypothesis and at most one cited finding.
4. A separate reviewer checks complete cited passages and accepts or withholds
   the proposed finding. A deterministic summary feeds the next planner decision.
5. The planner revises enquiries or stops. Replanning occurs only after all
   committed tasks complete; the parent cannot publish while children are running.

If a later plan selects execute but proposes no enquiries, the investigation
finishes with a recorded coverage limitation and publishes the reviewed draft.

Tasks execute serially to protect the case evidence database. Core owns admission,
routing, retries, and completion; the blueprint only proposes admitted task templates.
The default is at most three rounds, two enquiries per round, and seven child steps
per round. `dynamic_investigation.max_rounds` can reduce the three-round ceiling;
`hypotheses_per_round` can be one or two. These bounds permit at most 24 collector retrieval/
graph-view operations, plus up to six independent reviewer source searches and 16 investigation model decisions, including the final
stop decision. Legal relationship indexing has a separate bounded extraction
allowance; a source graph view may execute up to four native adjacency queries.
Investigation responses use `context_memory.policy.output_tokens` (2,048 by default), bounded by the configured model client. The same reserve is used for evidence admission and dispatch. The existing elapsed deadline applies;
cancellation and deadline checks occur at planning boundaries. Failed specialists
fail the workflow explicitly rather than producing a successful-looking draft.

The previous fully autonomous exploration implementation and its tests remain
available for future stronger models. It is not wired into the default DAG.
See [Preserved autonomous explorer](AUTONOMOUS_EXPLORER.md) for that implementation's
entrypoint, context protocol, limits, and historical usage.

## Evidence and coverage

With the context engine enabled, document searches retrieve complete structural
units from Membrane’s separate original-source corpus. The explicit disabled
profile uses the document skill’s SQLite FTS5 lexical search. Ranked matches are
not exhaustive; no match never proves absence. No neural source reranker is enabled.
The observed graph is built and integrity-checked before investigation; graph
associations and centrality do not establish identity, intent or wrongdoing.
Each finding is limited to 2,000 UTF-8 bytes of complete cited evidence for review.
Oversized and additional passages remain in the evidence ledger and are explicitly
counted as omitted from the assessor's packet. No passage is silently shortened
and treated as complete evidence. Unsupported findings are withheld.

UTF-8 text-like formats, CSV, EML, mbox, extractable PDFs and supported office
formats are normalized locally. Unreadable files remain in coverage. No OCR,
archive execution, audio transcription, external acquisition or legal action is
available. Defaults allow 5,000 files, 32 MiB per file and 256 MiB total bytes.
Potential privilege flags exclude affected passages from substantive findings;
automatic screening does not replace a human handling decision. Background
methodology is attributed, separate from case evidence, and never assumed to be
applicable law. Source authenticity remains unverified.

## Inspect reports and audit

Authoritative files remain in the SDK-provided Syncthing shared run directory:

```text
$MN_HOME/shared/submissions/<submission-id>/outputs/runs/<run-id>/
```

`output_folder` (default `~/Downloads/litigation-analyst`) receives an additional
host copy. `review_index.json` identifies `final_report.md`, `evidence_appendix.md`,
`graph_appendix.md`, source/index receipts and the evidence database.

Version 2.7.3 also publishes the three verified Markdown reports under the Job's
`context_sources/outputs/<run-id>/`. The existing document skill preserves full
report bodies and conversion hashes; repeated publication reuses unchanged files.
The SDK Job responder ingests these prepared sources into Membrane and returns
cited answers through `ask_job`. Case databases, originals, model requests and
checkpoints are excluded. Report sources become queryable after publication;
older completed runs retain their original output contract.

`case/rounds/` preserves immutable planner proposals, committed task parameters,
evidence observations, assessments, independent reviews, summaries and model
receipts. `case/agent_checkpoint.json` is the final review projection, retaining
the existing reporting contract; its mode is `dynamic_subworkflow`.
`case/source-query.json` records the separate original-source catalog; `case/rounds/models/*.memory.json`
keeps compilation witnesses outside model prompts. Dispatch, cancellation and
response receipts live in the authoritative Membrane Markdown store. Original bytes and normalized hashes/offsets remain under `case/`.
Only bounded coordination data and artifact references cross worker messages.
These artifacts are confidential; the response service does not expose them.
Assessment packets use the SDK context-budget helper to reserve guidance,
schema, and output capacity before admitting whole evidence records. Omitted
passages remain in the ledger and are excluded from visible citation IDs.

## Validation

```bash
python -m pytest tests/test_manifest_contracts.py -q
python -m pytest tests/test_litigation_analyst.py tests/litigation_analyst -q
node --test tests/litigation_analyst/*.test.cjs
python -m pytest tests -q
git diff --check
```

Deterministic tests exercise changed second-round plans, specialist ordering,
replay, cancellation, citation checks and preserved autonomous behavior. Live
runs additionally verify child completion and report replication between nodes.

The graph planner selects named chronology, sender, recipient, document or
source-clause relationship views.
Their RGQL is authored and validated by the blueprint; the LLM cannot submit arbitrary graph syntax.

## Filesystem runtime memory

`text_memory.enabled=true` uses authenticated Membrane TextMemory v1 and
CompileEvidence v2. Original normalized text stays in a separate source corpus
with frozen original hashes and revision-bound UTF-8 spans. Runtime decisions
use authored Markdown Facts, Relations and complete Notes. Retrieval stays within
`text_memory.max_context_bytes`; complete witnesses stay in run artifacts and are
excluded from model prompts. Historical memory is navigation, not legal or source
evidence. Required context still needs verified full-request token admission.
Set `text_memory.enabled=false` for an explicit memory-free profile. No retired
FileMemory adapter or automatic migration is provided.

## Context engine contract

This release declares `mirrorneuron-python-sdk[context]` in `dependencies.json`. Worker preparation requires the Membrane v2 client (>=2.1.0,<3); local source mode stages its matching source project. `mn.context` declares the Markdown profile, and `text_memory.enabled=false` explicitly disables recall. The context service stores Markdown revisions with one disposable DuckDB per job and uses CPU only. Set `MN_CONTEXT_ADDR` and `MN_CONTEXT_AUTH_TOKEN` through trusted runtime settings. Optional `MN_CONTEXT_OBSERVABILITY=true` logs authorized source and context content. No model compressor, Redis memory, or automatic migration is required.

Runtime navigation uses bounded native filesystem passage retrieval instead of
whole evidence bundles. Exact case citations still require the immutable case
source catalog; graph associations remain navigation. Selected external guidance
and runtime recall cross one final model-request boundary with separate receipts.

Version 2.3 originally linked completed runtime enquiries to their supporting and opposing
case passages, and those passages to immutable source revisions. Recall uses
bounded native DuckDB traversal before loading selected Markdown spans. The
sideband `case/rounds/*-memory-graph.json` records these navigation links. An
assessment remains inferred; graph relationships and historical notes cannot
replace exact case citations or independent finding review. Completed assessment
replay can finish interrupted link publication without another model call.


## Version 2.4 source and assembly boundary

Membrane is the Context Intelligent System. Complete original normalized text
and raw-file provenance belong to its separate source corpus. Case evidence IDs
retain exact character spans and SHA-256 in the frozen case ledger. Trusted
document adapters select whole paragraphs or numbered clauses using UTF-8 byte
locators, including clauses flattened onto one line; no original is rewritten or
executed. Lexical unit ranking is bounded navigation, not a semantic predicate
or exhaustive clause search. Explicit vector, graph and table modes keep their
native discovery; they are not silently replaced by lexical clause ranking.

Runtime knowledge contains authored qualified decisions, assessments and source
locators rather than original passage bodies. Every source locator includes its
physical corpus and pinned revision. Publication revalidates original bytes and
exact offsets. Runtime graph nodes are navigation; native dependency IDs do not
cross corpora. Facts and Relations tables support native DuckDB projection and
traversal, and complete Notes preserve uncertainty, competing explanations and
long structured outcomes. Publication clocks are durable and explicitly describe
runtime publication, not the date of the underlying event. Records are restricted
to round specialists. External methodology remains separately retrieved RAG.

Assessor admission preserves query rank and interleaves support and counterevidence.
Its complete evidence packet is limited by the shared source/runtime byte allowance
and the SDK’s conservative full-request capacity estimate. The default byte
allowance is 32,768; paired diagnostics retain 8,192. The 2,000-byte rule remains
a per-finding citation limit, enforced again by report validation; it does not
limit all evidence an assessor may read. Whole omitted units remain in the ledger
and cannot be cited. The final provider request still needs verified serving-token
admission; byte estimates and diagnostic JSON sizes do not establish serving tokens.

The separate source catalog is `case/source-query.json`. Runtime graph and
publication-clock receipts remain under `case/rounds/`; decisions use the shared
SDK authored-record writer. Existing staged runs and prior fixture versions remain
immutable; there is no automatic migration. Source-built matching Rust and Python
packages are required for the new byte-span contract; this change does not install
or deploy packages.

## Version 2.5 source relationships

The original-source adapter keeps numbered clauses and continuation paragraphs
whole. Explicit local section references, parent/subclauses and quoted defined
terms add dependency obligations. Missing/external targets remain coverage gaps.
Assessor admission keeps each clause and its dependencies together; independent
review receives the complete support closure of cited clauses. Both stages see
source-search coverage and use current evidence without historical memory.

`source_relationships.mode=hybrid` combines these deterministic relationships
with bounded index-time extraction of parties, obligations, conditions,
exceptions, dates and explicit cross-document references. The default extractor
inherits the configured LLM provider (`source_relationships.model=default`) with
`context_tokens=131072`; an explicit extractor model remains supported. It receives original units
without memory recall. Every proposed statement needs a unique exact quotation;
every edge target must resolve uniquely in the authorized frozen corpus.
Extracted relationships remain `model_proposal`, separate from observed source
structure and investigator claims. They do not establish legal effect or truth.

Defaults permit 256 extraction requests, at most 512 units per document and
24,000 UTF-8 bytes per extraction unit. Oversized units and failed or unresolved
extractions remain explicit gaps; they are not truncated. `mode=structural`
explicitly omits model extraction and marks that layer unsearched. Revision-bound
receipts avoid repeated extraction within a run. Cross-run cache reuse additionally
requires an immutable `@sha256:` model reference; a mutable model tag is cached
only within its run. Preserve the persistent file-identity ledger across captures.

The planner can request `clause_dependencies`, `qualification_paths`,
`amendment_paths`, and `clause_statements`, seeded by retrieved original clauses.
Traversal defaults to four hops and 49 edges. Paths retain relation type,
qualification and complete source exhibits. A bounded or incomplete search
cannot establish absence. Final prompt admission includes a path only with all
of its source support.

For manual validation, create a fresh source/index run with Membrane SDK 2.1 and
the updated graph skill. Inspect `case/source-relationships.json`, its hash in
`case/indexes.json`, source-view actions under `case/rounds/actions/`, and model
decision receipts. Check an exception/reference chain, an unresolved target and
an over-budget support group. Existing frozen indexes are not migrated. This
release makes no benchmark or measured answer-quality claim.


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

Exact source-span checks use the SDK RAG verifier. Case source selection, investigation state, legal interpretation and draft composition remain blueprint-owned.

## Version 2.6 document capability migration

Document conversion and frozen PDF-page extraction use the all-in-one
`mirrorneuron-docs-to-markdown-skill`. Office files use local MarkItDown.
Source searches use SDK SourceCorpus; `source_context.enabled=true` remains
independent of `text_memory.enabled`, which controls runtime recall. The index
receipt seals `case/source-query.json`; the removed passage index is not rebuilt.
The retained explorer exposes case-scoped `otterdesk.litigation.evidence` search,
verified-passage and frozen-PDF operations alongside the graph skill. Retired
index transformations are no longer offered. Existing staged runs retain their
implementation; new code does not resume or migrate their index/derivation audit.

## Standard MCP supervision

This package requires `mn.mcp.supervision.v1`. The SDK implements the shared manual, capabilities, context, results, activity, lifecycle, and operation tools. `knowledge/user_manual.md` is bundled with the prepared Job. Domain tools and their native JSON input/output schemas are declared once in `extensions/mcp.json`; response agents derive their bindings from it. All tool results use `mn.mcp.tool_result.v1`. Mutations require a request ID, and asynchronous work is observed through `get_operation_status`. Upgrade the installed SDK/API/desktop together and update idle Job definitions before using this contract.

Version 3.0.1 follows the registered default provider for both investigation and relationship extraction, applies the remote-provider hardware profile, and honors the configured investigation output reserve consistently during admission and dispatch. These are blueprint changes; no runtime upgrade or model-registry mutation is required. Normal run preparation remains SDK-owned and can prepare the selected gateway route. A bounded first-pass run may explicitly select structural relationships and one investigation round; its omitted extraction and investigation scope must remain visible.

Potential privilege labels (including “privileged and confidential”, attorney-client
communications and attorney work product) create conservative handling-review
flags. They are not a determination of legal privilege, and unlabeled material
still needs counsel review. Flagged content is withheld from relationship-model
extraction, substantive findings, the published evidence appendix and the offline
workspace. Frozen originals and internal audit records remain retained for the
authorized matter owner; they are not a cleared sharing package.

Remote-provider admission does not imply that the installed SDK supports that
provider’s serving-tokenizer protocol. The current SDK continues with unknown counts when counting is unsupported,
without replacing a registered remote default. Earlier blocked trials used an older
counting contract; their outcomes do not establish model factual accuracy.

The small synthetic regression matter is in
`examples/approval_reversal_case/inputs`; its seven files test amount-limited
approval, a full accounting reversal, an unconfirmed telephone account and
potential privilege. `expected.json` stays outside that input folder and is
never case evidence. `first-pass-config.json` records the bounded test scope;
this is a reproducible evaluation fixture, not an actual case or a completed
remote-model benchmark. Relationship-index policy version 2 invalidates older
extraction bindings that did not apply the handling exclusions.

Version 3.2 requires the companion SDK from 1.3.61.dev20 (or the matching local source checkout) for numeric ledger diagnostics and coordinated host delivery. Update the CLI alongside it. No Core configuration or model-registry change is required.

## Shared web report

The offline report uses `mn-web-report-skill` (distribution
`mirrorneuron-web-report-skill`) for the Geist shell, shadcn/ui controls,
Actions menu, tabs and non-modal evidence panel. Domain views and evidence rules
remain in this blueprint. Open `web/index.html` from a completed output; no
Node server, CDN or model call is needed to read it. Saved copies include the
shared assets. Markdown and structured evidence remain the authoritative outputs.

## Native block composition (5.0.0)

The four parent phases and four child-task templates use the stock SDK block
worker. Source capture, indexing, round planning/tasks and publication receive
native block contexts and explicit input ports. The old worker bindings,
runtime-context dictionary and `case_workflow` bridge have been removed. Core
still schedules the serial child tasks and enforces the three-round limit.

SDK checkpoints bind captured evidence to the Job, run and original configuration.
The source/index/terminal chain retains file hashes and exact source authority;
publication verifies it before rendering. A domain-operation postcondition also
checks published bytes on replay, so changing a saved report fails without
rerunning investigation. Final report projection is read-only: the terminal
phase persists the audit review once. An interrupted host export can retry
publication while reusing the completed investigation.

Coordination messages carry committed references. Large authorized case files
and workspace JSON retain streaming hash verification rather than inheriting
the common JSON store's 64 MiB file ceiling. Source limits remain 32 MiB per file
and 256 MiB total; optional UI failures still leave the report/workspace available.
The preserved autonomous explorer also consumes native contexts, remains
unregistered, and requires an explicit workflow change before use.

Use SDK and blocks >=1.3.61.dev26 with common >=1.3.61.dev25. Existing Docker and
model choices are preserved. Deterministic tests cover compiled parent/child
bindings, publication replay, file tampering, optional UI failure and interrupted
export; they do not qualify a live model, Docker graph engine or deployment.

Version 5.0.1 removes the separate ten-second default preflight cap so a model that
responds within its configured request timeout can pass readiness. Existing prepared
Jobs retain their frozen code and configuration; update the Job definition from this
blueprint before starting a new run. Retrying an old frozen run keeps its old cap.
