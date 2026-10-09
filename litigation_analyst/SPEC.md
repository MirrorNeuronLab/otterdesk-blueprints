# Litigation Analyst specification

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

Extraction uses a dedicated 128K-token Nemotron context with no historical recall.
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
