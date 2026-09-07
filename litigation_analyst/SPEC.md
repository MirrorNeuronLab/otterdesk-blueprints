# Litigation Analyst specification

Version 1.0.0. A bounded evidence-assistance workflow, not autonomous legal advice.

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
