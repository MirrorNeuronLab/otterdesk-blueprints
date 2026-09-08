# Architecture Advisor contract

Identity: `software_architecture_advisor`, version 2.1.2. Source: Spark `/home/homer/Sandbox/legal_case/software_architecture_advisor`.

## Inputs and policy

Exactly one of `repository_url` or `input_folder` is required by domain validation. The manifest exposes the alternative fields as optional because neither alone is mandatory. The default goal asks for an actionable boundary/coupling concern and counter-evidence. `graph_export` is optional and must refer to indexed source paths with exact line spans. Versions 1 and 2 retain supplied-evidence labels. No source repository file can override the operator's knowledge library or runtime configuration.

Defaults: 5,000 source files, 500 KB per file, 20 MB aggregate source bytes, 650-character windows, 200 non-merge Git commits; thirty chat-model calls (six reserved for final review), three rounds, three hypotheses per round, six distinct hypotheses, sixty graph/search operations, a twenty-minute investigation budget, twenty rows and top-three retrieval. Oversized/non-UTF8 files are reported as skipped; aggregate count/byte breaches fail capture. Symlinks, hidden/build folders and output artifacts are excluded. No source code is imported or executed. Public HTTPS GitHub acquisition disables hooks, templates, redirects, global Git configuration, credential prompting and submodules, with a 180-second timeout. Each acquisition retains its own checkout and captured HEAD.

## Workflow and boundaries

`capture_repository` → `investigate_architecture` → `publish_architecture_review`.

Steps contain only SDK contracts and `StepSpec` agent graphs. Specialist roles include repository examiner, child initializer, architecture planner, graph analyst, evidence retriever, hypothesis assessor, round reviewer and architecture review editor. Thin handlers use `mn-prototype-stateful-step-agent`; it owns invocation idempotency and durable output ordering. Workers return bounded summaries plus artifact references. Domain code owns source/architecture policy, lazy architecture projections, hypotheses, evidence validation and report semantics. Runtime only creates and persists SDK context. Core owns routing, retries, joins and logical completion.

The reusable `mirrorneuron-graph-analysis-skill` owns RGX subprocess execution, read-only guards, timeout/output limits and pinned binary preparation. Its digest-pinned public GAR runtime image is used unchanged; `mn-graph-engine` source is read-only. SDK RAG owns embedding adapters and the shared document/evidence mechanics. SDK model access owns transport and provider binding. The blueprint's model adapter owns request schemas, budgets and audit contents; it never implements a generic network client.

## Evidence graphs

Architecture families: symbols/references, dependencies, calls, types, control flow, data flow, state, schema, API, events, workflow, deployment, tests, Git, ownership, incidents, configuration, security, semantic responsibilities, and intent. An encoder-scoped embedding index is a separate retrieval layer. All twenty families are reachable through bounded investigation tools. Lazy generations use snapshot, collector, scope, dependency and model/encoder fingerprints. File locks prevent simultaneous duplicate graph publication; atomic pointers preserve the previous graph on failure.

Sources retain exact UTF-8 text and SHA-256. Every edge retains source evidence IDs, provenance kind and collector identity. Missing spans/endpoints fail ingestion or publication. RGX query receipts preserve raw rows, parameter values, generation, result hash and the exact edge-manifest hash used to join provenance. Counts are scoped to the captured graph; sampled lists do not prove absence. Model-inferred semantic labels remain inferred. No untrained RFM predictions are presented as architecture facts.

## Review contract

Planning selects only indexed modules and allowed families. Each hypothesis obtains graph observations and separate support/counter searches. Citation enums constrain structured JSON requests; application validation rejects invented citations. One malformed-output repair is allowed within the global call cap. An independent final model review covers every recommendation promoted to the roadmap. Unreviewed findings remain exploratory. Unknown architecture rules and unavailable views force inconclusive conclusions. Inconclusive final advice is limited to validation actions. Original model responses and any normalized verification rollback remain in the audit JSON for inspection.

Final publication rechecks source hashes and exact evidence spans and validates assessment citations. Knowledge guidance is a bounded local library (normally at most two cards and 1,200 UTF-8 prompt bytes), never evidence of a project defect. Suggested coding tasks verify findings and current revision before recommending a reversible change. Failed investigations retain raw investigation, model and event audit files and fail the worker; they are not reported as successful completed reviews. Partial reviews identify failed findings explicitly.

## Artifacts and execution

Canonical artifact paths are authored in `contracts.json`. Confidential large artifacts are durably stored under the run directory before specialist output. The source snapshot identifies its evidence graph and immutable sources under `evidence/snapshots/<snapshot-id>/`; graph generations and query audit remain available for review. The standard `outputs.folder_path` contract stages the completed presentation bundle in shared storage and lets the SDK copy it to `~/Downloads/{job_name}` on the submitting host. That bundle includes canonical report and prompt files, familiar `architecture_*` and `improvement_prompts.*` presentation names, a prompt index, and one copy-ready task per finding. No new REST server or standalone lifecycle is bundled.

All steps use `mn-agents.worker.python_docker@1`, sharing the run's durable data plane. The worker image includes the graph binary copied from the public digest-pinned GAR image; platform-declared agents, skills, and SDK components are installed by the platform. Blueprint launch does not require gcloud or Git credentials. No-input launch fails with an actionable request for a repository; the synthetic fixture is only an explicit example/test input. Offline mode is opt-in and never a live-provider fallback.

## Child workflow contract

`workflow.child_workflows.investigate_architecture` declares a planner, pre-admitted single-handler templates, input/output path mappings, and round/node bounds. The generated parent sink hands completion to Core; the parent remains running until the child stops. The parent exit has no direct worker route; Core triggers it only with the final mapped child output.

Each round alternates planning, atomic graph commitment, deterministic execution and a completion barrier. Only the planner can choose the next round, and no executing or completed graph is rewritten. Child identity, round and phase are public progress metadata; inputs, model text and evidence remain confidential artifacts. Workers never dispatch other workers or complete the parent.

Plan nodes select allowlisted graph operations and independent support/counter searches. New evidence may revise a hypothesis's module, family, statement and selected queries while retaining its ID. Repeated completed work does not justify another round. Hypothesis revisions and previous evidence remain inspectable even when the final review uses the latest revision.

Publication verifies exact frozen spans, hashes and citations for all final decisions. The report includes executive summary, observed architecture relationships, prioritized findings, alternatives, a three-phase roadmap, and explicit coverage limits. Knowledge cards are guidance, never project evidence. Priority is not measured severity or ROI. Runtime state is versioned and requires the matching SDK/Core deployment; static workflows retain their previous semantics.

## Bounded working context

Live model calls use the shared SDK `ContextSession` and Membrane `mn.context.working.v1` contract. Deploy the matching SDK and Rust context service together. Observations are recorded before selection; only a bounded working view enters each model request. Raw observations, packet manifests and response receipts remain under `context-memory/` (under `case/` for Litigation Analyst). Redis owns the durable paginated recall index; no complete job snapshot is restored into process memory.

The SDK accounts for fixed instructions, schemas, output reserve and safety margin, and the gateway enforces its confirmed serving window. Current decision constraints and exact final-review evidence cannot be silently dropped; impossible required sets return an explicit partition requirement. Unselected evidence remains available by exact reference and query. A missing item in the working view never proves absence. Source hashes and citations are verified independently before publication. Cache loss cannot repeat a successfully journaled model response. Offline/scripted execution remains deterministic and does not call Membrane.

Semantic retrieval binds explicitly to `huggingface.co/zenmagnets/Nemotron-3-Embed-1B-Q4_K_M-GGUF:Q4_K_M` by default, independently of the chat model. The default `litellm_proxy` embedding provider prepares that Docker Model Runner model and sends inference through the SDK's bounded FIFO embedding lane so first-use and cross-job requests do not contend directly for the model. The SDK verifies embedding capability before requests. `embedding.provider` and `embedding.model` remain operator-tunable; `default` is the chat route and must not be used for embeddings. Graph views and text embeddings are built lazily when an admitted child task needs them. A failed embedding build cannot publish a completed generation or a successful review.
