# Litigation Analyst specification

Version 1.1.0. A bounded evidence-assistance workflow, not autonomous legal advice.

The product accepts an optional legal-document folder and neutral investigation
goal. With no folder, a preparation script downloads EMC2 from the pinned
upstream GitHub revision. Custom invalid inputs fail. The default workflow runs
four logical steps on the declared Docker worker: prepare sources, build document/graph indexes, investigate
evidence, and write a review draft. Shared agents own replay and message APIs;
Core owns routes and logical completion. The graph_analysis_skill owns engine
invocation and published binary preparation. The original platform document
index remains a pinned dependency; the engine source is not modified or vendored.

Acceptance requires exact normalized-text SHA-256 and span provenance, durable
source snapshots, explicit unreadable coverage, read-only bounded graph queries,
CPU release telemetry, model/query/error audit records, bounded model-selected
enquiries, and a verified draft whose citations resolve to the frozen corpus.
Inputs must not be modified or uploaded. Reports, databases, model prompts and
source snapshots are confidential run artifacts. Only references and bounded
counts cross agent-message boundaries. Human review is required before reliance
or any legal/external action; the blueprint exposes no such action.

The source inventory includes original byte hashes as well as normalized record
hashes. Supported sources are UTF-8 text-like formats, mbox, EML, extractable PDF,
and office formats supported by the declared local converter. Unreadable files
remain visible in coverage; no OCR, archive execution, or silent simulated
success exists. Empty/no-readable-text custom inputs fail before model use.
The document skill's persistent SQLite FTS5 index supplies ranked lexical retrieval
and exact spans; it does not promise exhaustive or neural semantic retrieval.

Graph projection creates SourceArtifact, Email, Document, Mailbox, and extracted
Correspondent nodes with observed SENT/TO/CC/CONTAINED_IN edges. Centrality is
optional; heterogeneous PageRank is not a ranking of culpability or importance.
All model assessments remain inferred; unknown or invalid citations cannot enter
the final draft. Missing dependencies fail explicitly. Engine release 0.0.1 is
CPU-only; future CUDA use requires a separately verified release and truthful
profile reporting. Training a predictive RFM, legal conclusions, and autonomous
publication are non-goals.

Default bounds, storage layout, preparation prerequisites, and known format
limits are specified in README.md and configuration. Deterministic tests cover
input selection, source freezing, exact citation verification, graph safety,
follow-up lineage, worker replay, contract compilation and layer boundaries.

The LLM selects one action at a time: discover/read/invoke installed skills,
update a structured hypothesis, or finish. The blueprint owns prompts, authorized
bindings, hypothesis validation and final citation checks. The shared agent owns
manual discovery, argument validation, durable bounded execution and deadlines.
Graph mutations are unavailable to the agent. Original PDFs are re-extracted only
by observed source ID resolved to frozen bytes; page observations need normalized
passage IDs for report citations. Unknown evidence IDs cannot support hypotheses.
The JSON checkpoint is the authoritative decision/revision/tool/model audit;
SQLite is the evidence store and final hypothesis/report projection. Completed
observations are replayed; in-flight reads may repeat after an interrupted call.
Changed snapshot, config, model, manuals or descriptors reject resume. The agent
runs on the POSIX worker main thread. Limit/cancellation stops produce explicitly
partial investigative drafts, never a claim that all evidence was reviewed.

Planning and execution alternate through the shared PhaseCycle. Every model decision
receives attributed offline RAG guidance and structured action contracts. Default
limits are 5000 decisions and skill attempts with a 99,999-second elapsed deadline. Early finish
requires report submission and evidence-grounding review. Only accepted findings
enter the narrative; exact source and derivation checks precede deterministic export.
Reference knowledge is excluded from the evidence ledger. Guidance hashes bind resume.
Source handling flags exclude affected citations from substantive findings. Full
records, unresolved enquiries, failed actions and incomplete report reviews remain
visible. The step and worker timeouts are also 99,999 seconds, avoiding a shorter outer deadline.
The new source-index table requires rebuilding derived document indexes; old completed
run artifacts remain available and are never silently migrated or re-investigated.

## Bounded working context

Live model calls use the shared SDK `ContextSession` and Membrane `mn.context.working.v1` contract. Deploy the matching SDK and Rust context service together. Observations are recorded before selection; only a bounded working view enters each model request. Raw observations, packet manifests and response receipts remain under `context-memory/` (under `case/` for Litigation Analyst). Redis owns the durable paginated recall index; no complete job snapshot is restored into process memory.

The SDK accounts for fixed instructions, schemas, output reserve and safety margin, and the gateway enforces its confirmed serving window. Current decision constraints and exact final-review evidence cannot be silently dropped; impossible required sets return an explicit partition requirement. Unselected evidence remains available by exact reference and query. A missing item in the working view never proves absence. Source hashes and citations are verified independently before publication. Cache loss cannot repeat a successfully journaled model response. Offline/scripted execution remains deterministic and does not call Membrane.

The investigation adapter caps each model response at the context policy’s `output_tokens` (or a smaller provider limit). This keeps the reserved response space aligned with the working-memory budget; an inherited larger chat limit must not crowd out the first investigation request.
