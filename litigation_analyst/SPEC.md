# Litigation Analyst specification

## Version 3.3.1 navigation and disclosure

Expose eight primary task groups: Overview, Findings, Questions, Evidence,
People & events, Timeline, Reports and Review history. Preserve the original route
strings and saved-state contract; use explicit presentation grouping for comparison,
briefing and change/audit routes. Keep Matter settings secondary. Do not change
source authorization, review digests, human decisions or briefing eligibility.

Overview presents the existing record summary before counts. Findings exposes
withheld claims as correction work, never eligible briefing material. Evidence
puts search above the list and retains complete long names through tooltips/details;
technical provenance is secondary. Selecting a graph node retains the displayed
context, highlights its connections and exposes supported sources in a responsive
inspector. Keep active navigation visible after rerendering at narrow widths.

Group saved-copy/download actions under Export. Local review/saved-view edits have
an explicit pending-save reminder. Distinguish requesting a copy download from
verified filesystem persistence; reopening the downloaded copy restores the state.
Keep the existing recipient confirmation and complete supporting/contrary basis
for reviewed briefing export. This is presentation-only; no runtime/IPC/data
contract or model call is added.

## Version 3.3 reading presentation

Optional workspace publication adds source-bound reading reports, internal review
tasks and a selectable people/event/reference map. The authoritative investigation
and report are written first. Reading/render failures remain contained by the
existing optional preview status; they cannot fail domain completion.

Revalidate normalized hashes, exact spans and financial quotation bindings before
deriving this presentation. Preserve source observations, counsel annotations,
model assessments and human decisions as separate dimensions. Apply the existing
limited consistency guard to older projected findings; expose flagged drafts as
correction work and exclude them from reading findings and briefing eligibility.
No new finding or human approval is synthesized. The reading brief supplies
amount distinctions, accounting net qualifications and record-based review tasks.

Graph nodes describe distinct observed email addresses with header display names,
communication source records, annotated financial records and recorded transaction
references. Edges have exact source support; shared-source and header links do not
infer participation, causation, knowledge, payment or real-person identity.
Unknown dates stay unresolved. Cap projected communications/financial records at
60 each and addresses per header field at 20; cap displayed links at 49/nodes at
60, disclose truncation, and provide an equivalent connection table.

Markdown rendering supports headings, tables, blockquotes, lists and code with
inert HTML and allowlisted evidence drill-throughs. Reading reports cover the
authorized snapshot independently of analytical filters. Reviewed briefing export
must strip reading reports/tasks, the case map and reading-copy provenance along
with the existing full-source and unreviewed-state exclusions.

`render_review.py` is an offline presentation command for a completed workspace.
It writes a new separate folder only, binds provenance to the original workspace
hash and never rewrites frozen analysis, performs inference or publishes externally.
This additive presentation preserves the workspace v1/IPC/runtime contracts.

## Version 3.2.1 initial planning contract

Before a model chooses enquiries, verify the frozen indexes and supply a bounded
source inventory with deterministic examples spread across distinct normalized
sources. Admit complete short documents or whole structural units and their local
dependency closure; preserve exact source hashes/offsets and handling exclusions.
Selection is navigation, never an exhaustive review or a source of report findings.
Budget this packet together with schema, guidance, prior findings and output reserve.
Empty optional historical memory must not imply an empty current source corpus.

For revision zero the model schema permits only execute and requires a nonempty
enquiry list. Actual absence of authorized readable sources and inability to admit
complete source context produce explicit incomplete stop reasons without model
inference. Existing cancellation/deadline controls retain priority. Completed-round
replanning can stop as before. Prior run requests and artifacts are never rewritten.

Local models require at least one GPU with 49,152 MB of memory. When the selected default LLM is a registered remote provider, admission requires any GPU and 16 GB RAM; local-model VRAM constraints are removed through the existing SDK resource profile.

Version 2.7.5 requires the published graph analysis skill `1.3.49` and temporal
graph skill `1.3.60`. The verified runtime modules are unchanged; release-mode
setup resolves both capabilities through the declared package registry.

## Interactive investigation contract (2.7)

The primary deliverable is a frozen local investigation, `case/workspace.json`,
optionally rendered at `web/index.html`. Rendering failure removes stale previews
but preserves authoritative JSON, verified drafts and audit files. The batch
workflow connects findings → source comparison → relationship graph → email
chronology → evidence gap → reviewed work product. Wider specification gaps are
explicit in [the implementation report](IMPLEMENTATION_REPORT.md).

Findings have stable enquiry/section identity, source basis digest, revision,
origin, separate source/evidentiary/human-review dimensions, exact support and
counterevidence, alternatives, limitations, questions and gaps. Independent model
checking never becomes attorney review. Human decisions retain actor, time, exact
digest, wording and rationale; disagreement remains visible. Local decisions/views
persist through explicit HTML save or JSON review export/import, never confidential
browser local storage. Imported records are bounded and validated.

Job `state` stores the temporal skill's immutable source receipts and snapshot
history. Capture time is separate from event time. Changed source basis, wording,
counterevidence or gaps increments finding revision and requires reassessment.
Earlier approvals/wording are historical, never silently replaced. Old snapshots
whose sources are no longer authorized cannot enter the current projection.
Standalone contexts without trusted Job identity/storage disclose single-snapshot
mode instead of inventing continuity.

Membrane authored finding/locator records supply `SUPPORTED_BY`, `OPPOSED_BY`,
`CITES` navigation; original SourceCorpus units remain citation authority. Runtime
memory is historical navigation only. The temporal graph skill supplies closed
time-window order checks, bounded source-supported paths, immutable history and
distinct occurrence mechanics. Addressing never implies delivery, reading,
knowledge, continuous roles or transfer. Missing/conflicting Message-ID values
remain unresolved; hashes and file copies cannot invent occurrences.

Restricted/flagged content, counts, graph support and dependent conclusions are
removed before page generation. Mailbox containers with excluded members are not
copied. This is an authorized-owner local projection, not authenticated sharing.
Briefing export requires reviewed wording and recipient confirmation, includes
complete supporting/contrary excerpts and limitations, and excludes full sources,
originals, unrelated state and unreviewed findings. Copies cannot be revoked.

Source text is escaped as inert data. A hash-bound script CSP and `connect-src
'none'` block page network calls. Local charts have keyboard-accessible tables.
Preview and explicit global filtering are separate; global dimensions use AND
and address inclusion uses sender OR recipient. Known authorized counterevidence
outside analytical filters stays visible. One-sided subsets warn and block export.

Version 2.0.1 makes the downloadable EMC-2 sample available from the setup UI and
treats a blank optional folder as sample selection. Version 2.0.0 changed the
default investigation topology from one autonomous tool loop to an LLM-planned,
Core-managed child workflow. Input and final report paths
remain compatible. Existing runs retain their staged implementation; no old audit
is migrated or silently re-investigated.

## Product and ownership

The product accepts an optional legal-document folder and neutral goal. Omission
or a blank setup value selects the pinned public EMC-2 synthetic sample; invalid
custom inputs fail.
Four fixed phases prepare sources, verify document/graph indexes, investigate,
and publish a draft. The investigation parent initializes context; its child
planner commits enquiries using only declared templates. Core alone admits and
executes the graph and releases the parent output after the final stop plan.

The LLM selects enquiries, evidence searches, optional admitted graph views, assessments
and acceptance decisions. Workers execute committed tasks deterministically;
replanning occurs between completed rounds. Up to two enquiries per round and
three rounds produce at most seven steps per round. Evidence, assessment and
independent review workers run serially to avoid competing SQLite mutations.
Unchanged repeated enquiry work, or an empty execute proposal after a completed
round, stops with an explicit coverage limitation.
Model/validation/tool failures fail the workflow, not a simulated successful
investigation. Cancellation and elapsed deadlines are checked between rounds.

The SDK blueprint-support runtime owns exact structured-request replay, managed
context turns, response validation before atomic receipt persistence, and
context-capacity calculation. SDK RAG owns generic document indexing, evidence
spans, and query/document embedding adaptation. The graph skill owns bounded
read-only RGQL validation and binary preparation. `payloads/domain/round_model.py`
therefore contains only litigation prompt/policy composition over the shared SDK
decision helper. `payloads/domain/round_tasks.py` remains blueprint-owned because
its enquiry schemas, evidence admission, privilege exclusions, finding identity,
and review rules are litigation product policy rather than runtime mechanics.

## Evidence and review contract

Ingestion freezes original bytes and normalized text with SHA-256 and exact span
provenance, reports unreadable formats, and rejects symlinks and empty custom
corpora. The graph skill owns graph execution and binary preparation. Membrane
owns enabled original-source retrieval; source retrieval remains enabled independently of runtime recall.
Graph queries are read-only with literal LIMIT <=50 and case-scoped execution.

Every enquiry collects distinct support and counter searches. The assessor receives
complete, bounded passages and explicit omitted counts. SDK context admission
budgets the full schema and guidance before selecting whole evidence records;
omitted records cannot be cited by the assessment. The model's structured output
restricts citations to visible evidence IDs and preserves committed task IDs;
an empty evidence packet permits only an inconclusive assessment without findings.
No match is not evidence
of absence. Potential privilege flags exclude source passages from findings.
Assessments preserve uncertainty and ordinary explanations. Each finding cites
only visible verified evidence, at most 2,000 UTF-8 bytes, and a separate reviewer
must accept it before it enters narrative output. Final rendering revalidates
all retained source hashes and exact offsets. Graph results remain derived exhibits,
not allegations or independent corroboration. Attributed background guidance is
methodology, never evidence or an assumption of applicable jurisdiction.

## Artifacts and compatibility

Version 2.7.3 publishes verified `final_report.md`, `evidence_appendix.md` and
`graph_appendix.md` through the declared Docs to Markdown skill into the Job's
`context_sources/outputs/<run-id>/` folder. SDK/Membrane own incremental ingestion,
whole-source querying and citations. The blueprint owns this report allowlist;
case audit files, originals and model receipts are not conversation subjects.
Publication follows final citation verification and is required when the runtime
provides a Job output folder. This adds prepared report outputs without changing
investigation decisions or authorizing legal action. Existing frozen runs are
unchanged.

Version 2.7.1 corrects the index phase deadline for bounded sequential model
extraction: `build_case_indexes` and `investigate_case_evidence` allow 99,999
seconds. The 256-request default extraction budget, per-unit bounds and provider
deadlines still apply. This is an operationally compatible patch with unchanged
inputs, artifacts and evidence policy. Previously accepted runs retain their
frozen controls; Core checkpoint retry reuses validated run-local decisions.

Version 2.7.2 removes worker deadline overrides so executable workers inherit
their logical phase controls, including the long index deadline and bounded
600-second child tasks. The supported investigation adapter uses the accounted
SDK structured-result method, retaining provider error classification and exact
usage on invalid responses. SDK dev52 or later is required. Inputs, evidence
policy, model-request shape and artifacts remain unchanged.

Version 2.0.2 sets the default host export to
`~/Downloads/litigation-analyst`, matching the declared job name. Previously
submitted jobs retain their configured destination.

Immutable proposals, task inputs, evidence, assessments, reviews, round summaries
and model receipts live in `case/rounds/`. A final checkpoint projection preserves
the existing citation-checking and rendering interfaces. Evidence SQLite, source
inventory, original bytes and normalized sources retain their existing contracts.
Authoritative reports remain on SDK-provided Syncthing shared run storage; Downloads
is an additional host export. Messages carry artifact references and bounded counts.
Core and shared agent lifecycle own replay and task completion; SDK working context
owns durable provider receipts. Raw evidence never enters the response service.

The previous autonomous explorer remains in `domain.app.agentic` and
`domain.research.investigate`, including its tests and historical documentation.
It is not an automatic fallback and has no default workflow binding.

## Acceptance and limits

Tests must compile admitted child templates with Docker workers; demonstrate an
LLM-directed second round informed by earlier observations; preserve stable
hypothesis identity; reject tampered task references, unsafe queries and invented
citations; withhold rejected findings; prove completed work replay does not invoke
models again; and retain the autonomous explorer's existing regression suite.
Live acceptance observes actual child tasks through report completion and matching
shared-file hashes on both nodes, using `default` → Nemotron on Spark.

Outputs are drafts for human review. Legal advice, source authentication, exhaustive
search, OCR, external acquisition/contact, legal filing and autonomous publication
are non-goals. Failed and incomplete investigations are never presented as verified
legal conclusions.

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

Version 2.3 originally published runtime enquiry → support/opposition passage → source links
after validating and committing an assessment. Links pin canonical revisions and
explicit dependencies, retaining source authenticity and interpretation limits.
Bounded RAW → GRAPH → RAW recall supplies historical navigation; original case
passages remain the sole citation authority. Link publication is idempotent and
resumes after completed assessments without repeating inference. Existing runs
retain their staged implementation and immutable audit.


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

## Persistent file identity and selective memory

Physical source graph identities use the shared graph-analysis file registry.
Entity UUID, raw-file content_hash, current_path and previous_paths are separate
properties. Preparation freezes the current identity map in source_inventory;
indexing consumes it without reading mutable originals. A case-owned, locked
ledger retains identities across successive source captures. Scope is an explicit
investigation.repository_id or trusted job identity, with a persisted workspace
identity when no stable repository/job identity exists. Rename matching prefers
Git observations, then unique disappeared/new exact raw-file hashes. Ambiguous
matches remain separate. RGX's integer logical_id is an opaque checked handle for
the full UUID; consumers cannot infer a path or content from it. Embedded mailbox
messages, correspondents and version-bound citation IDs retain their existing
contracts. Existing graph databases are never overwritten; a new source/index
run is required. Preserve the ledger to retain preexisting rename history.

Historical recall is explicitly enabled for plan decisions only. Assess and
review decisions do not fetch or assemble runtime notes and reserve no recall
envelope; complete current source evidence has their full input allowance.
Validated decisions still publish through the shared SDK for future planners.

## Version 2.5 source relationship index and paths

Use Membrane SDK >=2.1 whole-unit discovery with a blueprint-owned legal adapter.
Preserve clause continuations, explicit local section references, parent/child
qualifications and quoted defined terms. Preserve original offsets and bytes;
ambiguous, external and unsupported references stay explicit. Selected clauses
and their complete dependency closures form atomic prompt-admission components.
Propagate search status and unresolved coverage to assessment and independent
review. Review all dependencies of cited clauses, not only the cited excerpt.

Seal `case/source-relationships.json` into the index receipt. Clause identities
bind persistent physical file UUID, normalized source revision and exact offsets;
file UUIDs remain stable as graph and content revisions change. Hybrid indexing
adds separately qualified model proposals for source statements and references.
Require exact unique source quotations and uniquely bound authorized targets;
never promote these proposals to observed facts or established legal effect.
The graph projection keeps observed structure, proposals and investigator claims
distinct. The existing document/email graph and graph backend remain in use.

Extraction uses the configured default LLM in a dedicated 128K-token context with no historical recall; an explicit `source_relationships.model` overrides that selection.
Default bounds are 256 index-time requests, 512 units per document and 24,000
UTF-8 bytes per unit. Capacity, malformed extraction and unresolved targets mark
incomplete coverage. Structural mode explicitly disables extraction. Cache keys
bind job/scope, file identity, source revision, offsets and extractor/model
version; cross-run reuse requires immutable model identity. Mutable aliases
permit run-local replay only. These requests are separate from the investigation
decision allowance, and request counts do not imply provider retry counts.

Named source views bind seeds to retrieved original clauses and use shared typed
traversal over native adjacency. Enforce relation/direction, four-hop and 49-edge
defaults with authorized provenance for every edge. Expose ordered paths,
unresolved frontier and coverage; never report bounded omissions as absence.
Hydrate complete path exhibits and transitive structural support, and admit
each path with its sources as one component. The LLM cannot author arbitrary
RGQL. Fresh indexing is required; existing frozen artifacts are never rewritten.


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
provider’s serving-tokenizer protocol. Evidence decisions retain verified context
admission and fail explicitly when a verified counter is unavailable; the
blueprint never replaces a registered remote default with a local model. The
2026-10-18 mini trial is blocked at that prerequisite in the installed SDK; no
remote-model report or factual-accuracy result is claimed from that attempt.


## Version 3.1: counsel-directed first review

The default `review.profile=first_pass` performs one round (up to two enquiries),
uses observed structural relationships, and limits investigation decisions to six.
A separate harmless readiness decision checks the selected model before source
acquisition or case inference. It sends no case material, preserves the configured
provider, and fails with `case/model_preflight.json` when verified-context admission
is unsupported. The 10-second setting bounds the model request after readiness;
SDK preparation can take longer. Platform input staging occurs before this check.
No local-model fallback is used. The installed remote serving-tokenizer prerequisite
still applies; this release does not change the SDK or runtime.

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


## Version 3.2 reliability and delivery

Legal clause boundaries must start a line; decimal amounts and embedded references
such as TX-104 cannot start clauses. Keep exact normalized bytes and offsets.
Candidate packets include complete short authorized sources and source-bound
financial annotations. Whole-component admission still determines actual visibility.
Never expose flagged sources, omit a required cited dependency, or let an omitted
financial record masquerade as reviewed. Review performs its own source search and
one structured financial consistency check per finding when annotations exist.
Reject missing/duplicate checks, unresolved record coverage and contradictory claims.
The deterministic explicit-absence guard is limited and is not semantic validation.

Primary reports lead with the counsel issue brief and source-linked financial
records; technical graph/action detail remains available under advanced disclosure.
Inventory-matched ledger/policy work is internal reread; privilege-related work is
handling review. No automatic collection, contact, legal judgment or assignee is
introduced. New workspace coverage lists actual assessor/reviewer source admission
and full-source admission separately from source readability and AI acceptance.
`case/consistency_review.json` and `case/performance.json` are additional diagnostics.
Frozen prior runs are never rewritten by this release.

Blank input retains the pinned EMC-2 revision and CC-BY attribution. Repository
README.md, LICENSE.md and CITATION.MD are excluded only for this known sample;
custom folders retain their own selection. Report native attachment extraction gaps,
archives not extracted and duplicate normalized-source groups without collapsing
source identities. Source-linked expected criteria live outside model inputs in
examples/emc2_evaluation/expected.json; exact-binding checks require separate
attorney judgment for narrative retention and substantive correctness.

The SDK/CLI resolve completed output identity from the bound Core result reference,
retain completion/file readiness checks, and deliver the configured Downloads copy.
Host delivery receipts and latest.html are separate from immutable analysis files.
Stage timing and recorded response usage support prospective response-budget
comparisons. Unmeasured provider reasoning/calibration/repair overhead stays unknown;
output-token defaults are unchanged pending a passing factual and attorney baseline.

Version 3.2 requires the companion SDK from 1.3.61.dev20 (or the matching local source checkout) for numeric ledger diagnostics and coordinated host delivery. Update the CLI alongside it. No Core configuration or model-registry change is required.

## Report presentation

`mirrorneuron-web-report-skill` owns common report chrome and component assets.
The blueprint owns its domain-specific views, source scope and evidence semantics.
The web page is local/offline with a minimal header, Actions dropdown, progressive
tabs and a non-modal evidence Sheet. Presentation adds no model calls, source
execution, external sharing, runtime changes or approval authority.
