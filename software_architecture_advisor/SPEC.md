# Architecture Advisor 3.1 specification

## Outcome

Turn a captured repository into a traceable architecture review covering the
23 sections and 150 aspect contracts in `payloads/report_specs`. Every aspect
gets an applicability decision independently of coverage. Missing evidence,
failed tasks and capped source packets remain visible; they never imply health.

## Execution contract

The fixed parent workflow captures source, analyzes dependencies, investigates
architecture through Core-owned child rounds, then publishes the review.
The deterministic planner commits bounded task references. One specialist
invocation performs one OpenCode skill review in OpenShell. Each round is serial
and replanning occurs only after its tasks have terminal durable results.
The planner itself makes no model calls. No worker owns routing or completion.

The planned content consists of source scans, 150 aspect analyses, 150 independent
challenges, bounded dynamic evidence follow-ups, 23 section syntheses and a final
executive synthesis. Defaults: 1,024 total tasks and model attempts, 20 rounds,
64 tasks/round, 64 follow-ups of maximum depth two, and 604,800 seconds (one week)
for both the parent investigation deadline and planner walltime budget. Capacity
is reserved for synthesis; remaining source omissions are recorded. Each call
has a 600-second timeout, 1 MiB output ceiling and 60 KB UTF-8 prompt bound.
Source packets have exact offsets and are at most 24 KB, including long Unicode
lines. A run can stop earlier for budgets and still publish a partial report.

## Model selection

`opencode.model` is operator-configurable and exposed in the setup guide. Its
default is `opencode/muse-spark-1.3-contributor-free` (Muse Spark 1.3 FreeOpenCode
Zen). The alternate `spark/muse-glimmer-30b` (Muse Glimmer 30BLocal Spark) uses a
sandbox-local OpenCode custom provider with the configured `opencode.spark_base_url`.
Both display labels normalize to their provider/model IDs. The model and provider
endpoint are pinned in the durable run context. The OpenShell policy admits the
Zen API and the local Spark chat-completions endpoint; other endpoint changes
require a corresponding policy change. No host OpenCode configuration is copied.

## Evidence and content

The bundled catalog validates every aspect file against its original SHA-256.
The context pins catalog digest, source manifest, configuration and objective.
Source inventory equality and hashes are verified on load and publication.
Models select supplied evidence IDs; the worker resolves those to exact frozen
file hashes, character offsets, line ranges and excerpts. Invented or out-of-scope
citations and unresolved report IDs are rejected. Source is never executed.

Aspect prompts contain the full applicable specification, shared conventions,
and a requirement-by-requirement answer contract. Prior validated results and
source spans are selected within a hard prompt bound; whole omitted records are
counted. Challenges receive the corresponding analysis and other evidence.
Section and executive synthesis use bounded prior results, with omissions
reported. Inferred summaries retain their source task references.

Claims distinguish observed, derived, inferred, assumed and proposed information.
Confidence includes rationale and remains separate from priority, urgency,
effort and impact. Recommendations and work packages are created only from
model-proposed, validated, traceable records; missing recommendations are not
replaced with automatic generic remediation. Unresolved challenges require
verification before implementation. Runtime measurements and actual test runs
are never inferred merely from source presence.

## Durability and failure semantics

SDK committed artifacts protect plans/results from conflicting rewrites.
Task request identities and SQLite attempt reservations make duplicate delivery
safe; an interrupted attempt cannot automatically consume another model call.
Core supplies the execution barrier and durable shared run directory. OpenShell
synchronizes shared artifacts through Core's storage contract. No separate host
copy or native execution fallback is implemented by the blueprint.
Malformed/model failures are blocked task results, while corrupted committed
artifacts fail validation. Offline mode explicitly means not analyzed. Partial
reports state the terminal reason, task status and source omissions.

## Deliverables and acceptance

Publish report Markdown/JSON; 23 section files; coverage for 150 aspects and
all source packets; canonical evidence, claims and findings; recommendations,
assumptions, verification tasks, roadmap and proposed implementation work
packages. All material record references must resolve. All cited source spans
must match captured bytes. Work packages contain baseline, actual files,
evidence, constraints, non-goals, migration steps, tests, acceptance and stop
conditions. Report generation does not authorize implementation.

Tests must exercise more than 300 tasks using actual SDK child-plan contracts,
round barriers, dynamic work, final executive ordering, replay, failure/budget
handling, Unicode bounds, exact citation validation, all aspect/section outputs
and report tampering. A small opt-in live OpenShell test verifies the default
OpenCode provider without launching hundreds of external requests.

## Limits

Static source review is not runtime measurement, a security audit or a guarantee
of architectural correctness. Language-specific structural extraction may be
incomplete; the text reviewer can still assess supported polyglot source.
Bounded relevance selection may miss cross-cutting interactions. Unknown or
omitted evidence must remain explicit. OpenShell shared-storage transfers are
serial and may dominate runtime for very large captured source inventories.

The packet reviewer uses an explicitly built OpenShell image context at
`payloads/openshell_worker`, including `iproute2` for isolated networking.
SDK image preparation installs declared dependencies before sandbox creation.
The reviewer imports uploaded blueprint modules from its invocation workdir.

Parent-phase Docker workers use a single-stage Python 3.11 image without
`USER` instructions, allowing SDK skill-preparation hooks to add native tools.
OpenCode and sandbox system setup belong to the separate OpenShell image.

### Immutable review handoff

The owner planner persists stable tasks, bounded prompts, evidence selections,
configuration, and SQLite reservations before dispatch. Pending reservations count
toward `max_calls`; ambiguous execution is never automatically refunded. Frozen
admission JSON is published with the runtime run ID through SDK artifact helpers.
Reviewers use isolated attempt workspaces and publish task-specific result files.
They have no writable budget database or owner catalog mirror. The next owner
planning pass reconciles only Core-committed result receipts, verifies citations
against the frozen owner snapshot, then publishes domain receipts idempotently.
This migration retains serial dependencies and does not introduce parallel review.

Owner publication exports the validated report, section documents, work packages, and JSON task audit to the declared output folder. SQLite reservation state is excluded from that export.

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

## Retry budget and evidence contract

Manual Core checkpoint retry preserves completed logical steps/child tasks and
uses the original workflow and source inputs. Required domain metadata declares
only bounded retry-adjustable budget/timeouts. Owner-local domain steps declare
idempotent internal writes; OpenShell review execution requires verified handoff
state before replay. Completed model requests use committed domain receipts;
uncertain attempts remain blocked.

Domain retry helpers apply explicit effective allowances and subtract durable
run-wide consumption. Frozen source capture, investigation context and request
artifacts remain immutable evidence. A replayed source-capture boundary verifies
its committed request and snapshot instead of ingesting the source again.

## Context engine contract

This release declares `mirrorneuron-python-sdk[context]` in `dependencies.json`. Worker preparation installs the Membrane v2 client (>=2.0,<3); local source mode stages its matching source project. `mn.context` declares the Markdown profile, and `text_memory.enabled=false` explicitly disables recall. The context service stores Markdown revisions with one disposable DuckDB per job and uses CPU only. Set `MN_CONTEXT_ADDR` and `MN_CONTEXT_AUTH_TOKEN` through trusted runtime settings. Optional `MN_CONTEXT_OBSERVABILITY=true` logs authorized source and context content. No model compressor, Redis memory, or automatic migration is required.
