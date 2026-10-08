# Architecture Advisor

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

Architecture Advisor 3.5 reviews code repositories piece by piece with the
OpenCode skill inside OpenShell. It evaluates the supplied report library's
**150 aspects in 23 sections**, including an independent counterevidence review
for each aspect, and produces explicit coverage even when evidence is missing.

## Run

Run the default MirrorNeuron repository review:

```bash
mn blueprint run ./software_architecture_advisor
```

To review a local repository instead:

```bash
mn blueprint run ./software_architecture_advisor \
  --set inputs.payload.repository_url= \
  --set inputs.payload.input_folder=/absolute/path/to/repository
```

The default URL is `https://github.com/MirrorNeuronLab/MirrorNeuron`. Supply exactly one
source: a public HTTPS GitHub repository root or a local folder. The platform
stages local input; reviewed source is never imported or executed. Capture
includes code only: Markdown, other documents, JSON/YAML/TOML data, and sample
data files are ignored. Documentation, examples, samples, fixtures, dependencies
and build directories are excluded by `ingest.exclude`; this includes Elixir
`deps` and `_build`. `mix.exs`, `config/*.exs` and ordinary test code are included.
Only captured code enters source packets, retrieval and model review. Public Git
clones retain the existing bounded, credential-free acquisition policy.

Default model: **Muse Spark 1.3 FreeOpenCode Zen**
(`opencode/muse-spark-1.3-contributor-free`). Override with
`--set opencode.model=provider/model`; update the OpenShell provider/network
policy for a different provider. There is no automatic paid-model fallback.
Bounded source excerpts are sent to the selected provider. OpenCode public
sharing, edits, shell execution, delegation and web tools are disabled for review.

The platform prepares `mirror-neuron/software-architecture-advisor:local` from
`payloads/docker_worker/Dockerfile` using the standard Python 3.11 base with
the declared SDK, agent and skill packages. This single-stage Dockerfile has no
`USER` instruction, as required by the SDK skill-preparation hook contract. The OpenShell reviewer builds its own declared context at
`payloads/openshell_worker/Dockerfile` before sandbox creation. It includes
OpenCode 1.18.33, Python and `iproute2` for network isolation; the platform
installs declared packages into that image. An existing Docker-worker image
tag is not used for sandbox provisioning. The execution host needs Docker and a working OpenShell gateway.
Do not launch the packet worker natively; live calls verify the OpenShell runtime.
The sandbox policy permits OpenCode Zen and the configured Local Spark model endpoints. Model changes
may require an explicit policy and credential-provider change.

## Choose the model

The blueprint setup form includes **OpenCode review model** with two choices:

| Choice | `opencode.model` |
| --- | --- |
| Muse Spark 1.3 FreeOpenCode Zen (default) | `opencode/muse-spark-1.3-contributor-free` |
| Muse Glimmer 30BLocal Spark | `spark/muse-glimmer-30b` |

Change `opencode.model` in `config/default.json`, or override it per run:

```bash
mn blueprint run ./software_architecture_advisor \
  --set opencode.model=spark/muse-glimmer-30b \
  --set inputs.payload.repository_url= \
  --set inputs.payload.input_folder=/absolute/path/to/repository
```

Both display labels are also accepted as configuration values. Local Spark uses
`opencode.spark_base_url` (default `http://10.0.4.32:8000/v1`), matching this
workstation's OpenCode provider configuration. The worker writes only the selected
provider configuration inside the sandbox. Changing that endpoint also requires
updating `payloads/openshell_worker/policy.yaml`; the sandbox must reach the local
server. Model selection is frozen for the run; change it before starting a new run.

## Workflow

1. Capture immutable UTF-8 source text, file hashes and available Git revision.
2. Build the existing source-linked dependency baseline and bounded DSM.
3. Initialize a durable task catalog and execute Core-managed child rounds:
   source packets → 150 aspect analyses → 150 challenges → evidence-driven
   follow-ups → 23 section syntheses → executive synthesis.
4. Revalidate evidence and publish the final report and linked registers.

Each worker handles one task and returns a bounded artifact reference. Core owns
execution, dependencies and round barriers; workers do not dispatch other
workers. Serial dependencies within a round protect shared output synchronization.
The planner admits new follow-ups only for known packet IDs with evidence from
completed parent tasks; duplicates, unsupported references and depth beyond two
are rejected. At most 64 dynamic follow-ups are admitted.

The default ceiling is 1,024 tasks/calls, 20 rounds, 64 tasks per round and seven
days (604,800 seconds). The parent investigation deadline and planner walltime
budget both allow one week. A small repository still plans **324 catalog tasks
plus source packets**.
Each source packet is at most 24,000 UTF-8 bytes; each model prompt is at most
60,000 bytes. Each call has a 600-second deadline and 1 MiB output ceiling.
Large source inventories reserve capacity for report synthesis and record omitted
packets explicitly. Lower call/time budgets produce partial reports, not positive
health assessments. Full reviews can take hours; the defaults are ceilings.

Configuration is in `catalog_review` and `opencode`. Existing capture limits are
5,000 files, 500 KB/file and 20 MB aggregate; tune `ingest` for larger repositories.
Unsupported extensions, symlinks, excluded directories and oversized/non-UTF-8
files retain capture limitations. Polyglot code reviews do not require Python
modules. The declared BEAM analysis skill installs pinned,
offline syntax parsers for Elixir/Erlang module declarations and dependency
candidates, alongside Python import extraction. Elixir lexical aliases, grouped
aliases, import/require/use/behaviour and module references, plus Erlang
behaviour/import/remote references, produce exact source-linked edges. Unresolved
references and syntax failures remain visible. Other automatic syntax layers
(function calls, types, state and control/data flow) remain Python-only and
record that limitation for Elixir/Erlang. Macros, generated code, preprocessing,
dynamic dispatch, process messaging and supervision topology are not verified.
Optional graph exports must cite captured code; ignored documents cannot supply
source evidence. Metadata-only deployment/ownership collectors need explicit
code-linked exports when their source files are outside the code-only capture.

`offline=true` is an explicit orchestration/coverage check. It makes no OpenCode
calls and marks all tasks `not_analyzed`; it never substitutes synthetic findings
for failed live analysis. Model failures or malformed citations become blocked
task records. Attempt reservations prevent automatic re-execution after an
interruption; use a new run for an explicitly chosen retry.

## Results

Authoritative artifacts remain in the SDK-provided shared run directory under
`$MN_HOME/shared/submissions/<submission-id>/outputs/runs/<run-id>/`. The SDK
handles the configured convenience copy to `~/Downloads/architecture-advisor`.

- `report.md`, `report.json`, `review_index.json`: overview and navigation.
- `sections/`: 23 reports with per-aspect requirements, conclusions and challenges.
- `coverage.json`: all 150 applicability/coverage decisions and source packet scope.
- `evidence.json`, `claims.json`, `findings.json`: immutable locators and traceability.
- `recommendations.json`, `assumptions.json`, `verification_tasks.json`:
  proposed decisions and the evidence still needed.
- `roadmap.json`, `work_packages.json`, `work_packages/`: proposed migration
  sequences and self-contained, evidence-linked coding-agent briefs.
- `catalog/`: immutable plans, requests, attempt budget, results, receipts and
  terminal reason. This audit data is confidential.
- `analysis/dependencies.json` and optional `analysis/dependency-dsm.csv`:
  deterministic structural evidence.

Empty recommendation/work-package registers mean no supported proposal was
produced. They do not mean the system is healthy. Runtime behavior, security,
capacity, organizational ownership, history and business costs remain unknown
unless supplied evidence supports a carefully scoped claim. Proposed work is
never authorization to change source, production data or deployments.

The complete original specification library is bundled at `payloads/report_specs`
with its manifest and hashes, so jobs do not depend on the author's host path.

## Validation status

The orchestration, evidence validation and report publication checks pass. The
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
take precedence; otherwise `source_search.mode=hybrid` uses the declared encoder
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
