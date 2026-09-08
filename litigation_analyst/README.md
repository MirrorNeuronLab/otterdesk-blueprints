# Litigation Analyst

A Docker-worker blueprint converted from `litigation_analyst_v2` on Spark.
It freezes legal sources, builds a persistent document index and observed graph,
then lets an LLM choose investigative enquiries using installed skill manuals.
A deterministic final stage validates citations and writes a review draft. All outputs remain drafts for human review.

## Prepare and run

Requires MirrorNeuron with the companion SDK, agents, and skills checkout,
Docker, Git, authenticated GitHub read access to `MirrorNeuronLab/mn-graph-engine`,
and an authenticated `gcloud` account with read access to
`mirrorneuron-public-packages/mn-graph-engine`. The new graph-analysis skill
must be installed from the companion checkout until its next package release:

```bash
export MN_WORKSPACE_ROOT=/path/to/mirror-neuron-set
export MN_SKILLS_ROOT="$MN_WORKSPACE_ROOT/mn-skills"
python -m pip install -e "$MN_SKILLS_ROOT/graph_analysis_skill"
cd litigation_analyst
python prepare.py
MN_USE_LOCAL_SKILLS=1 mn blueprint run ./
```

No input values are required. Preparation downloads the pinned synthetic
[EMC2 dataset](https://github.com/jur1st/emc-2) and the published, checksummed
MN Graph Engine 0.0.1 Linux binary. An omitted runtime `input_folder` downloads
EMC2 into that run's sample directory automatically. The configured local model
is selected and prepared by the SDK/DMR integration. Missing model service,
package, binary, or source inputs fail explicitly.

For your own documents, set the optional `input_folder` run input to an existing
local folder in OtterDesk. Optionally set `goal` and `output_folder`.
`python prepare.py --input-folder /path/to/case` selects an existing sample folder without
fetching EMC2 and records the folder in `prepared/inputs.json`; pass that folder
in your launch inputs, for example:

```bash
MN_USE_LOCAL_SKILLS=1 mn blueprint run ./ --set inputs.payload.input_folder=/path/to/case
```

Platform local-input staging makes it visible in Docker.
A typo or empty custom folder never silently substitutes demonstration data.
Do not place generated output inside the input folder.

The graph skill selects ARM64 or x86-64 from the selected worker’s advertised CPU architecture. The engine is CPU-only and requires glibc 2.36 or newer (Debian 12). The skill’s preparation hook owns the pinned provider wheel, NumPy, CPU PyTorch and checksummed GAR engine. It uses host credentials before staging; credentials and Git checkout metadata never enter the image. The provider supplies content-addressed retrieval, not trained litigation weights.


The graph skill is new source work. `MN_USE_LOCAL_SKILLS=1` uses the companion skill and agent
checkouts; a production non-development installation requires publishing their
graph skill version 1.3.23 first (existing dependencies retain their published versions). Preparation does not publish packages.

## Inputs and limits

The folder is recursively inventoried. UTF-8 text, CSV, Markdown, JSON, XML,
HTML, logs, `.eml`, and `.mbox` are read locally. Text PDFs use the shared PDF
extraction skill; supported office files use the shared AnyDoc converter.
Image-only PDFs, images, archives, unsupported encodings and conversion failures
are explicitly listed as unreadable. There is no OCR, archive unpacking, audio
transcription, legal classification, or exhaustive search.
Extract those sources to text before relying on coverage. Source documents are
never executed. Symlinks are rejected.

The default bounds are 5,000 files, 32 MiB per file, 256 MiB total source bytes,
5,000 skill attempts and 5,000 model decisions, with a 99,999-second overall investigation
deadline (`max_investigation_seconds: 99999`). The agent can finish early; these are
ceilings, not targets. Individual graph calls and model requests retain timeouts.
Graph queries require LIMIT <=50. Operator tunables are in `config/default.json`.
Retrieval uses the document skill's persistent SQLite FTS5 lexical index with
exact text spans. It replaces the previous transient hashing retrieval in this
workflow; ranked results are not exhaustive or semantic search.

The agent reads packaged SKILL.md manuals through `read_skill`, then selects
registered operations with `invoke_skill`. Direct deterministic callers use the
same Python implementations. No skill is installed at runtime. Installed wheel
and editable packages carry the same manuals and descriptors.

Hypotheses track cited support, counter-evidence, alternative explanations,
uncertain identity, inferred assessments and outstanding enquiries. Evidence
cannot grant tools or override instructions. Only the frozen case can be queried.
Creation/import are restricted to the deterministic ingestion stage.

The shared bounded loop stores each decision before dispatch and each completed
observation before another model call. Completed calls are reused on restart;
an interrupted in-flight read may repeat. Evidence/configuration/manual changes
reject checkpoint reuse. Cancellation (`case/cancel.request`) is checked between
actions; POSIX main-thread deadlines bound blocking calls. Terminal partial
reports state cancellation, exhausted budgets and unresolved enquiries explicitly.

## Inspect outputs

Outputs live in the SDK-provided platform run directory on shared storage.
The configured output folder (default `~/Downloads/litigation_analyst`) receives
an additional host copy. `review_index.json` locates:

- `final_report.md`: neutral hypotheses, findings, citations, limitations and coverage.
- `case/source_inventory.json`: original file hashes, normalized source identities,
  sizes, and unreadable sources.
- `case/sources.json`: frozen, exact text used by every character-span citation.
- `case/evidence.sqlite3`: sources, cited evidence, current hypotheses and reports.
- `case/agent_checkpoint.json`: model requests/responses, actions, results, errors, manual hashes and hypothesis revisions.
- `case/documents.sqlite3`: persistent read-only passage index.
- `case/indexes.json`: source and index integrity receipt.
- `case/originals/`: original file bytes, named by SHA-256.
- `case/evidence.rgx`: observed document/email graph, built and checked before agent execution.

Draft citations refer to normalized text hashes and exact character offsets.
Mailbox citations refer to decoded message headers/body text; original container
hashes remain in the inventory. Converted documents likewise retain original
file hashes and a separate extracted-text hash. Model assessments are inferred
review material; extracted email relationships do not establish identity,
knowledge, intent, liability, privilege, authenticity, or admissibility.

Review the database with a read-only SQLite connection. The response service is
for bounded role/setup questions, not confidential evidence or audit access.
No email, filing, publication, payment, or other external action is available.

## Validation

```bash
python -m pytest tests/test_manifest_contracts.py -q
python -m pytest tests/test_litigation_analyst.py tests/litigation_analyst -q
python -m pytest tests -q
git diff --check
```

Live model and Docker checks are opt-in; deterministic tests use synthetic
sources and scripted models, retaining exact-span and audit assertions.

Live investigation uses Membrane's bounded working memory instead of a growing
history prompt. Every completed observation is persisted before the next decision.
`recall_memory` retrieves older observations; `read_memory` verifies the frozen
artifact before returning an exact bounded range. Skill manuals remain durable
and their relevant portions can be recalled. Source validation still owns case
citations. The generic SDK owns context limits and durable model receipts.

The investigation emits action-started, action-completed, and action-failed events
for the monitor. These show bounded query previews, concise stated purposes,
validation failures, and successful Rust graph row counts. Full actions and
evidence remain in `case/agent_checkpoint.json`; evidence bodies and manuals are
not copied into the event feed. Existing runs retain their original worker code;
start a new run to use updated activity events.

The default customer destination is `~/Downloads/litigation_analyst`, configured
through `outputs.folder_path` and copied back to the submitting host by the SDK.
`final_report.md` contains the evidence-based investigation report;
`review_index.json` identifies the audit root, and `runs/<run-id>/` preserves each
run's report and audit files. The report quotes validated source spans with source
IDs, SHA-256 hashes, and offsets; graph results are explicitly derived exhibits.
No prose is generated during final report assembly. Missing hypotheses and
budget-limited coverage are stated explicitly.

## Planning, guidance and reviewed reporting

Investigation alternates persisted planning and execution phases. Each enquiry states
its question, prior findings, evidence sought both for and against the hypothesis,
and completion criteria. After at most six skill attempts the agent must review the
enquiry before further tools. Exact repeated immutable operations reuse their prior
result; the attempted action still counts against the finite budget. Four decisions
are reserved after skill-budget exhaustion for finalization, within the decision cap.
Older action previews are accessible through paginated `read_investigation`.

Every LLM request includes locally retrieved reference guidance with source URL,
section, review date, applicability, and content hash. The independent SDK RAG package
owns SQLite FTS5 retrieval; `payloads/domain/knowledge/guidance.json` owns the curated
NIST/DOJ/Federal Rules background and separately labeled blueprint policies. This is
lexical retrieval with no embedding service, network lookup, or runtime installation.
Guidance is not case evidence or a determination of applicable law. The jurisdiction
and historical edition are not assumed. Missing/invalid guidance fails explicitly.
Changes to the guidance fingerprint reject checkpoint reuse.

The document skill supports paginated source discovery, exact contextual spans,
ROT13 decoding with original offsets, and complete bounded CSV decimal totals.
Duplicate text copies are grouped in ranked results. Potential privilege flags block
substantive report use pending human handling review; automatic text flags are only
an initial screen, and the investigator can flag additional sources.

The LLM proposes citation-linked findings, then reviews them against complete cited
passages in a separate model decision. Only accepted findings enter the narrative.
This model review is not a guarantee of truth or independent source authentication.
Final citation/derivation validation and Markdown rendering are deterministic.
`final_report.md` contains concise findings, chronology, subject assessments,
counter-evidence, integrity limitations and follow-up. Exact passages and full graph
results live in `evidence_appendix.md` and `graph_appendix.md`. Incomplete reviews
withhold proposed narrative findings. Prior runs remain under `runs/<run-id>/`.

The investigation's workflow control and Docker command timeout are both 99,999 seconds. Source mode
uses updated sibling packages; binary mode requires publishing and installing builds
containing the new document operations, agent phases and RAG lexical index.

The investigator exposes only currently allowed phase actions to the model and
enforces the same list before dispatch. Current phase, active plan, latest error,
and recovery instructions are retained in a separate control block. Reading skill
manuals and updating hypotheses remain available while collecting evidence;
starting another enquiry requires review of the active enquiry. Repeated errors
and lack of substantive progress use the shared agent's checkpointed recovery
guard. Exhausted recovery records `investigation_stalled` and preserves collected
evidence for the deterministic partial review draft. Planning and log volume do
not themselves count as investigation progress.

## Shared runtime preparation

Graph binaries, provider wheels, NumPy and CPU PyTorch are owned by the graph analysis skill. The SDK invokes its `mn.worker.prepare` hook before staging build contexts; neither this blueprint’s Dockerfile nor `prepare.py` prepares them. Use `MN_USE_LOCAL_SKILLS=1` with the companion workspace until the updated skill is published. The optional `prepare.py` only acquires/selects EMC2 input and writes its input descriptor. Worker architecture comes from the selected runtime, not the host running that script.

### Bounded context compatibility

Version 1.1 requires the SDK `ContextSession` and Membrane `WorkingMemory` RPC from the companion workspace. Update SDK, Membrane and Core together before launching a new live run; existing run bundles retain their original behavior. Redis is required for durable recall. Context is an evictable cache over immutable evidence, with run-wide storage/call quotas and explicit incomplete coverage. The operator may increase the window within confirmed model and hardware capacity. No package publication is performed by this change.

The investigation adapter caps each model response at the context policy’s `output_tokens` (or a smaller provider limit). This keeps the reserved response space aligned with the working-memory budget; an inherited larger chat limit must not crowd out the first investigation request.

Available skill identifiers and the current manual-read registry are required working context, alongside action schemas and approved operations. Context selection cannot evict the identifiers needed to discover and invoke a skill.

For a two-node deployment, the authoritative report and evidence files stay in
`$MN_HOME/shared/submissions/<submission-id>/outputs/runs/<run-id>/` on the
Syncthing shared filesystem. The SDK supplies that run directory to workers;
blueprints must not replace it with a node-local Downloads path. Syncthing
replicates the shared tree to the other node. The configured `output_folder`
provides an additional convenience copy on the submitting host.

Each decision's system instructions identify the current execution phase and
allowed actions. Recalled decisions are historical observations; the managed
memory packet's `current` object owns the active enquiry and skill/manual state.
