# OtterDesk Blueprints

Python workers use Python 3.12, matching the MirrorNeuron runtime and SDK. Python base images select 3.12; CUDA, ROS Jazzy, and OpenShell images verify that minor during their build. The ROS detector retains PyTorch 2.7.1 and CUDA 12.8 through matching Python 3.12 wheels.

`otterdesk-blueprints` is a self-contained OtterDesk-facing worker blueprint catalog. Each blueprint folder includes
its own manifest, configuration, payloads, README, and user-facing `SPEC.md`.

VC Assistant, Financial Advisor, Litigation Analyst, and Research Assistant
use foundational `mn_sdk.llm` calls through blueprint support; they do not
depend on the deprecated LiteLLM communication skill. Their RAG packages and OCR skills
own model specifications and use the SDK runtime model wrapper, while each
blueprint declares only its product-level behavior and required skills and SDK packages.

All published blueprints declare the Markdown context profile.
CCTV, Architecture, Litigation, VC and Mac security investigator use Membrane v2
runtime recall. Drug Discovery uses Membrane source intelligence for input, output
and procedure questions; other blueprints disable worker context consumers. General
Assistant retains its own Job-private Harness2 context inside OpenShell. See
[the catalog audit and runtime prerequisites](CONTEXT_ENGINE.md).
Every active context consumer prepares Membrane SDK 2.1 and the v2 RPC service.
The shared runtime readiness check rejects older engines before submission;
the Markdown record label `mn.context.text.v1` remains valid on v2.

## Quick Start

List available blueprints:

```bash
mn blueprint list
```

Run a catalog blueprint:

```bash
mn blueprint run <blueprint_id>
```

Run a checked-in folder directly:

```bash
cd <blueprint_id>
mn blueprint run --folder .
```

Run repository tests:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-test.txt
.venv/bin/python -m pytest -q
```

Handler contract tests import source payloads while executing in temporary
workdirs. Dependency session files must remain outside catalog packages.
Test subjects resolve only inside this catalog checkout. Retired Legal Assistant,
Purchasing Manager, and SMTP GTM identities are checked for absence rather than
borrowed from sibling packages. Procurement checks use `procurement_manager`;
the local, unpublished GTM pair has synthetic AgentMail approval, replay, draft
integrity, stop, suppression, and uncertain-send coverage.

See [Runtime DAG Flow Patterns](DAG_FLOW_PATTERNS.md) for the catalog's
event-driven, fork/join, service, and linear flow contracts.

Run-input configuration uses the shared SDK block helpers in
`mn_sdk.integrations.block_inputs`. `@/` means the blueprint root, for example
`@/examples/sample_inputs`; ordinary staged relative paths use the worker root.
The SDK owns default/override merging, linked input paths and immutable saved
input artifacts. Blueprint hooks retain domain normalization and validation.
Use an updated SDK and reprepare existing Job definitions after this change.
See [shared block ownership and the catalog audit](SHARED_BLOCKS.md) for the
remaining runtime, evidence, file, and publication boundaries.

## Persistent co-worker conversation

Every published blueprint declares the stable Job response service. After
hiring, OtterDesk can ask bounded questions about the co-worker's role, safe
configuration, schedule, and latest work when it has never run, is idle,
paused, scheduled, completed, failed, or archived. Sending a question never
starts the target co-worker.

Core owns this response service outside the workflow DAG. It uses sanitized Job
context and Job-scoped knowledge, never a blueprint-defined service node or
command, and excludes credentials, private source data, and unrestricted
artifacts from its responses.

The catalog contract tests also expect this repository to live beside the companion
`mn-skills` and `mn-agents` folders because they import shared blueprint support
helpers and render shared agent templates.

## Catalog

Categories are Business (finance, legal, procurement, and office work), Research
(scientific research), Engineering (software and cybersecurity), Physical AI
(cameras and robots), and Other (miscellaneous). `category.json` defines the
ordered taxonomy; each manifest references its category in `extensions/product.json`.

| Blueprint | Category | Purpose |
| --- | --- | --- |
| [`general_assistant`](general_assistant/README.md) | Other | General task solving with the default model, 32 GB RAM and private Harness2 improvement in OpenShell. |
| [`gtm_planner`](gtm_planner/README.md) | Business | Plans marketing work and publishes bounded collaboration packets. |
| [`gtm_executor`](gtm_executor/README.md) | Business | Executes approved marketing work through declared tools and Job collaboration. |
| [`drug_discovery_research_assistant`](drug_discovery_research_assistant/README.md) | Research | Runs one discovery cycle, evaluates five distinct molecules, writes a review packet to `~/Downloads/drug-discovery-research-assistant`, and completes. |
| [`ct_reader`](ct_reader/README.md) | Research | Experimental NVIDIA CT reader with Chat uploads and local NIfTI preview. Not for real diagnosis. Requires one NVIDIA GPU with 48 GiB memory. |
| [`research_assistant`](research_assistant/README.md) | Research | A research assistant that combines deterministic evidence and verification stages with an isolated OpenShell worker for autonomous goal refinement, tool-driven exploration, hypothesis generation, and bounded generated-code experiments. |
| [`software_architecture_advisor`](software_architecture_advisor/README.md) | Engineering | A read-only architecture advisor with hundreds of OpenCode/OpenShell review tasks, dynamic follow-ups, 150 report aspects, cumulative snapshot data, an offline dashboard, evidence and proposed work packages. |
| [`code_verifier`](code_verifier/README.md) | Engineering | Creates editable software rules, waits for your approval in Chat, then verifies each with source evidence and confidence. |
| [`procurement_manager`](procurement_manager/README.md) | Business | Procurement Manager compares supplier evidence, lifecycle costs, and purchase options and prepares a review-only decision packet. Its stable blueprint ID remains `purchasing_manager`. |
| [`mac_security_investigator`](mac_security_investigator/README.md) | Engineering | Reviews local Mac unified logs across user-initiated scans with source receipts and saved reports, without inspecting OS files. Pilot; see its current limits. |
| [`cctv_operator`](cctv_operator/README.md) | Physical AI | A steerable NVIDIA CCTV co-worker with secure approved-stream setup, live preview, Cosmos3 sequence understanding, Markdown activity memory, and qualified risk predictions for chat. |
| [`microduck_controller`](microduck_controller/README.md) | Physical AI | Lets an OtterDesk user control the live Microduck MuJoCo simulation in ordinary language through bounded MCP actions, deterministic ball navigation, and stoppable continuous free play. |
| [`litigation_analyst`](litigation_analyst/README.md) | Business | Investigates legal-document folders with exact citations, bounded hypotheses, graph tools, and a draft audit trail. Defaults to public EMC2 sample data on Docker workers. |
| [`financial_advisor`](financial_advisor/README.md) | Business | Reviews financial documents and prepares a grounded advisory packet. |
| [`vc_assistant`](vc_assistant/README.md) | Business | Produces early diligence reports from startup document packets. |
| [`ros_amr_controller`](ros_amr_controller/README.md) | Physical AI | Operates the warehouse robot simulation through bounded MCP controls. |

## Folder Contract

Most blueprint folders contain:

| Path | Purpose |
| --- | --- |
| `README.md` | Self-contained quickstart, inspection notes, and validation guidance. |
| `SPEC.md` | User-facing problem, outcome, evaluation criteria, limits, and upgrade path. |
| `TERM.md` | Terms, assumptions, or domain notes when present. |
| `manifest.json` | Canonical blueprint/v1 identity, semantic release version, and role-document references. |
| `workflow.json` | Logical topology and workflow policies. |
| `execution.json` | Agents, workers, runtime requirements, services, and schedules. |
| `contracts.json` | Inputs, outputs, artifacts, validation, status, and privacy. |
| `extensions/` | Versioned platform and product descriptors. |
| `config/default.json` | Default launch configuration and mock/sample inputs. |
| `config/overwrite.json` | Optional local overrides. Do not commit customer secrets. |
| `knowledge/` | Optional reference documents, seeded and indexed by the runtime for conversation RAG. |
| `payloads/` | Worker code, prompts, policies, fixtures, and support files. |

Blueprints that retain knowledge, RAG, or application state across executions
declare `resources` in `extensions/storage.json` through `mn.storage`. Core creates one
stable job-data directory per hired/configured job:

```text
$MN_HOME/job-data/<job-id>/
  knowledge/
  databases/rag/
  state/
```

The bundle's knowledge seed is copied only when the stable job is initialized
or explicitly reset. Later runs share that directory and never overwrite user
edits. Run inputs, outputs, logs, and artifacts remain run-scoped. Two jobs
created from the same blueprint receive different job-data directories and RAG
databases.

The standard payload layout places product policy in `domain/` and logical
collaboration graphs in `steps/`. Native block compositions use SDK workers and
can leave `runtime/` and `agents/` empty. All thirteen catalog packages use native
blocks. Docker, native-host, OpenShell,
and Beam worker assets stay as sibling payload directories (`docker_worker/`,
`openshell_worker/`, or `beam_modules/`) rather than nested under a script
wrapper. Python workflow steps are launched with the shared SDK module
`python3 -m mn_sdk.step_runtime`.

Python handler steps use module-only references such as `steps.research`; the
shared `mn_sdk.step_runtime` entrypoint calls that module's `run()` function.
Keep DAG topology in `workflow.json` rather than duplicating it in blueprint-local
dispatch code or configuration handoff lists.

## Safety Checklist

- Review `manifest.json`, `payloads/`, and `pass_env` before live runs.
- Start with mock, dry-run, or quick-test settings before enabling real external services.
- Keep customer-specific inputs and secrets in local overrides or environment variables.
- Update the local blueprint README and `SPEC.md` when behavior, inputs, outputs, or limits change.
- Declare durable resources by logical name, validated relative path, access
  mode, and optional `@/` bundle seed. Never declare or accept a host path.

## Canonical packages

`index.json` is an ordered list of published package paths. Names, descriptions,
versions, requirements, and product information come from each package's documents.
Catalog reads validate data without importing Python code or preparing resources.
All folders and ZIPs use `https://mirrorneuron.io/schemas/blueprint/v1/manifest.schema.json`.
Use `mn_sdk.blueprints.read_blueprint`, `resolve_config`, and `compile_blueprint`;
`open_blueprint` adds ZIP extraction and `export_blueprint` preserves the full package.
External dependencies remain declared; offline vendoring is optional.

The `software_architecture_advisor` blueprint accepts a public HTTPS GitHub repository URL or local source folder and combines structural analysis with bounded OpenCode review tasks inside OpenShell. It publishes 23 report sections covering 150 aspects. See [Architecture Advisor](software_architecture_advisor/README.md).

SDK workflow capabilities are declared in the `packages` array in
`dependencies.json`; domain skills remain in `skills` and agents in `agents`.
Every package and skill declaration uses `type: "pip"`, `source: "gar"`, its full
Python distribution name, and a pinned release version. For example:

```json
{"type": "pip", "source": "gar", "name": "mn-python-sdk-rag", "version": "0.1.0"}
```

Local installation resolves SDK packages from `mn-python-sdk/packages` and skills
from `mn-skills` or this blueprint's `payloads/skills` projects by distribution
name, ignoring the declared release version. Local setup enables
`MN_USE_LOCAL_SKILLS=1`. Binary mode retains GAR pins and does not select bundled
skill source automatically. The same declaration works in both modes; source
paths are prepared by the SDK rather than authored in dependency records.
Each blueprint activates only its declared SDK capability closure.

## Shared conversation knowledge

Every blueprint may include a root `knowledge/` directory of reference documents.
The SDK stages it as a Core-owned seed for the isolated Job `knowledge/` resource
and enables RAG by default when documents are present. An explicit `mn.rag.enabled:
false` opts out of retrieval. Existing explicit knowledge seeds must be migrated
rather than combined silently with a second root seed.

The response service prepares the index and retrieves relevant knowledge for
capability, findings, and explanation questions, alongside current Job evidence.
Documents are reference data, not executable instructions or live observations.
Mark fictional fixtures as synthetic in each document. Actual findings come from
current evidence or declared read tools. Adding a seed does not overwrite an
existing Job's documents; existing Jobs need an explicit knowledge import or update.

## Dependency ranges

MirrorNeuron Python dependencies in `dependencies.json`, execution configuration,
and worker requirements use `>=1.3.47`. Bundled demo distributions are versioned
`1.3.47` and their declarations use the same minimum. Third-party libraries retain
their own version families (for example `numpy>=2.3.5,<3.0`). Package identity
versions and container image digests remain concrete artifact identities.

## Bibblio marketing services

[`gtm_planner`](gtm_planner/README.md) and [`gtm_executor`](gtm_executor/README.md) form a local MCP-connected marketing pair. Ideas and final emails require separate human approvals. Contacts and AgentMail credentials stay private to the executor. Hire and configure both, then explicitly start them when ready.

## Runtime activity

Use `mn_sdk.report_activity(message, kind="action", level="info",
owner_blueprint=..., step_id=..., run_dir=...)` for actual domain work and
observed findings. `kind` is `action`, `result`, `finding`, `milestone`, or
`diagnostic`; `level` is `debug`, `info`, `warning`, or `error`.
Use `mn_sdk.activity_operation(message, completed=...)` around a synchronous
domain operation when action/result reporting is sufficient. Do not define
blueprint-local formatters, publishers, stdout prefixes, or event clocks.
The SDK supplies the canonical `mn.runtime.event.v1` envelope with identity,
UTC timestamp, blueprint owner, run, step, and agent attribution. Existing
shell/native protocol records are normalized by Core at publication.
Only report observed facts; unchanged frame sampling and model bookkeeping
belong in diagnostics. Full outputs remain in artifacts.


## Standard Job MCP supervision

Every blueprint declares the required `mn.mcp` extension independently of
`mn.response`. The versioned profile is `mn.mcp.supervision.v1`; the public
endpoint is `/api/v1/jobs/{job_id}/mcp`. The prepared Job stores the installed
manual from `knowledge/user_manual.md`, its SHA-256, and its declared tool
schemas. Discovery works before a run and while a domain service is offline.

The SDK MCP component owns these common tools: `get_user_manual`,
`get_capabilities`, `get_job_profile`, `get_job_context`, `get_run_status`,
`get_run_results`, `start_run`, `pause_run`, `resume_run`, `stop_run`,
`watch_job_activity`, and `get_operation_status`. `ask_job` and `get_job_turn`
are optional conversation tools. Asking never starts or resumes work. Reads
without a run ID select the latest run and return an explicit empty run when
work has never started. Pause preserves resumability; stop cancels execution.
Run controls accept only runtime-issued execution IDs belonging to the bound
Job. Output IDs remain distinct from Job and execution IDs.

Domain tools use unprefixed verb-resource `lower_snake_case` names, descriptions,
native JSON argument types, input/output schemas, and effect annotations.
Shared names are reserved. Readiness, service selection, activity, and async
completion bindings belong in the declaration. The SDK stages the manual and
registers, validates, and wraps declared tools; blueprints implement domain
behavior. Domain polling uses the same `get_operation_status` public surface.

Every ordinary result uses `mn.mcp.tool_result.v1` in `structuredContent`, with
`tool`, `request_id`, `job_id`, `blueprint_id`, `run_id`, `status`,
`operation_id`, typed `data`, and structured `error`. Operation states are
`accepted`, `running`, `completed`, `failed`, `cancelled`, `superseded`, and
`timed_out`; actual workflow state stays in `data`. Acceptance is not observed
completion. Mutations require caller-generated request IDs; durable Job-scoped
claims deduplicate identical retries and reject conflicting reuse. Operation
polling stays bound to its original Job and run. MCP input-required responses
continue to use the existing MRTR protocol.

Launch credentials travel only in authenticated, main-process-supplied
`_meta["mn.launch"]` request metadata, validated through the existing launch
contract. They are excluded from advertised arguments, tool results, logs,
conversation history, and durable operation records. REST and MCP transitions
use the same SDK integration helper; Core owns actual execution state. The API
owns authentication, endpoint identity, and owner routing.

This is a coordinated replacement with no public compatibility aliases.
`get_latest_run` is replaced by `get_run_status`; `free_play` is renamed
`start_free_play`. Configuration, scheduling, approvals, retries, and destructive
data management retain their existing APIs. GTM peer collaboration retains its
separate read-only capability and gains no lifecycle authority.

## MCP Skills

The supervision server implements the stable
[`io.modelcontextprotocol/skills` extension](https://skills.extensions.modelcontextprotocol.io/specification/stable/skills)
on MCP 2026-07-28 and later. `server/discover` advertises the extension and
resources support. `skills/list` and `skills/get` return a complete, private
cacheable manifest; `resources/read` serves exactly its declared files. Optional
`resources/directory/read` supports bounded directory exploration. Unknown skill
URIs, cursors, and resource paths return `-32602`.

The SDK generates one `skill://<blueprint-name>/SKILL.md`, the installed
`references/user_manual.md`, and `references/tools.json`. Each manifest entry
includes its exact UTF-8 byte size and SHA-256 digest. The prepared Job's blueprint
revision and manual remain authoritative even when the catalog changes or a
worker is offline. Loading a skill grants no action permission. Live readiness
still comes from `get_capabilities`; runtime receipts establish completion.

## MCP support by blueprint

All 15 packages support the twelve common supervision tools above and one
installed supervision Skill. Optional conversation tools follow `mn.response`.
The catalog has thirteen published packages; GTM planner and executor remain
unpublished. Domain controls are listed below.

| Blueprint | Additional domain tools |
|---|---|
| CCTV operator | Read status/activity, video history/summary and benchmarks; answer video questions; change monitoring instructions; acknowledge notices |
| Microduck controller | Read duck state; move, perform a routine, find a ball, start free play, stop; set locomotion/posture, play ball actions, reset the simulation |
| ROS AMR controller | Read robot status, navigate to a zone, cancel navigation, adjust motion |
| CT reader | Common supervision |
| Drug discovery research assistant | Common supervision |
| Financial advisor | Common supervision |
| GTM executor | Common supervision; separate read-only peer collaboration |
| GTM planner | Common supervision; separate read-only peer collaboration |
| Litigation analyst | Common supervision |
| Mac security investigator | Common supervision |
| Procurement manager | Common supervision |
| Research assistant | Common supervision |
| Software architecture advisor | Common supervision |
| Code verifier | Common supervision |
| VC assistant | Common supervision |

Each package has its own `tests/test_mcp_<blueprint>.py` module. These validate
the installed manual and Skill digests, advertised schemas, never-run behavior,
run controls, deduplication and identity checks. The three domain packages also
exercise forwarding, asynchronous completion and their real worker registries.

The MCP-enabled packages require the coordinated SDK family from `1.3.61.dev12` onward, below `2.0`. That floor accepts the matching local source revision and final `1.3.61` release; local installs keep their real SCM versions.

## Code verifier

[`code_verifier`](code_verifier/README.md) reads a local
repository checkout or source/docs folder, extracts software expectations into
editable `rules.md`, asks the supervisor to approve the full list in Chat, and
verifies each approved rule separately against captured source.
Its report table includes pass/fail/unknown, exact evidence references and 0–1
confidence. Add or override rules in Job `knowledge/rules/*.md`; replace mode
uses only a supervisor-edited list. Source and tests are never executed.

The blueprint uses the static-code-analysis and code-search skills. Its additive
offline `TextSearchIndex` API needs the code-search skill release
`>=1.3.61.dev5,<2` before binary distribution; local mode uses current sibling
skill source. No runtime changes are required.

## Reusable block composition

**All thirteen catalog packages use stock blocks with direct native domain hooks.**
The catalog gate rejects legacy entrypoint wrappers and blueprint-owned capability
adapters. Shared blocks own execution receipts, effect reconciliation, managed
model access, native-device transport and verified file publication. Core owns
scheduling, joins, child workflows, physical delivery and accepted event-state
transitions. Blueprints retain their domain formulas, evidence qualifications,
prompts, review authority and report content.

The offline catalog regression (`python -m pytest tests vc_assistant/tests -q`)
passes **1,378 cases with 29 skips** at this source checkpoint. SDK CI passes
3,571 cases at its existing coverage floor; the block gate passes 473 cases at
its existing floor. Installed SDK dev34 / blocks dev33 / common dev30 test
candidates execute and replay all four compiled CCTV workers in fresh processes,
with synthetic resident/model transports and real JPEG/MP4 preparation. Earlier
installed-package probes cover Litigation's child workflow, all 21 VC specialists
and Microduck's native binding. These are source/test candidates, not releases.

Current packaged Python, measured against `HEAD` before this migration:

| Blueprint | Before | Current | Change | Python files |
| --- | ---: | ---: | ---: | ---: |
| Architecture Advisor | 9,241 | 7,158 | -2,083 (-22.5%) | 79 → 50 |
| CCTV Operator | 6,893 | 6,046 | -847 (-12.3%) | 44 → 46 |
| Code Verifier | 1,354 | 1,321 | -33 (-2.4%) | 30 → 15 |
| CT Reader | 247 | 193 | -54 (-21.9%) | 8 → 6 |
| Drug Discovery Research Assistant | 3,590 | 2,887 | -703 (-19.6%) | 46 → 23 |
| Financial Advisor | 3,462 | 2,796 | -666 (-19.2%) | 46 → 23 |
| Litigation Analyst | 6,604 | 6,687 | +83 (+1.3%) | 79 → 62 |
| Mac Security Investigator | 752 | 593 | -159 (-21.1%) | 24 → 11 |
| Microduck Controller | 3,884 | 3,810 | -74 (-1.9%) | 23 → 16 |
| Procurement Manager | 4,223 | 3,859 | -364 (-8.6%) | 34 → 17 |
| Research Assistant | 3,131 | 2,782 | -349 (-11.1%) | 34 → 17 |
| ROS AMR Controller | 5,925 | 5,935 | +10 (+0.2%) | 32 → 34 |
| VC Assistant | 9,294 | 8,344 | -950 (-10.2%) | 69 → 55 |
| **All thirteen** | **58,600** | **52,411** | **-6,189 (-10.6%)** | **548 → 375** |

These counts cover `payloads/**/*.py`, excluding directories named `tests`.
Vendored test files shipped directly inside payload directories are included in
both baselines. Repository tests, shared dependencies, documentation and generated
files are excluded. Retained custom domain policy is included.
The size audit retains two small increases: Litigation's case-source,
terminal-decision and audit-database integrity checks exceed its removed wrappers
by 83 lines; ROS adds a 10-line domain hook recording completed service shutdown.
Those product-specific checks remain in the blueprint. The catalog-wide reduction
includes their full cost and both staged Microduck source copies.

All thirteen catalog blueprints declare the existing `mn-blueprint-blocks` package.
Single-specialist phases declare blocks in `extensions/blocks.json`; custom
collaboration graphs keep their `StepSpec` and bind each specialist to the stock
SDK worker. Core continues to schedule joins, child workflows, native Compose
projects and the camera event loop. Domain hooks retain product decisions,
evidence rules, prompts, native protocols and report content.

New blueprints should start with the smallest suitable existing block, including
structured assessment, report publication or native computation when their
contracts fit. Custom policy compositions use domain-operation hooks. Declare
inputs, outputs, hook references, package versions, deadlines and call limits once.
Do not add local agent factories or another workflow runner. Keep domain hooks
small by calling focused policy functions and existing skill APIs. Custom code is
appropriate for specialized review authority, native protocols and domain policy.
Canonical declarations get a compiler lock; inline workers use an explicit
blueprint release revision and installed package pins. These are distinct revision
contracts, and an inline binding does not claim canonical lock verification.

Each blueprint may opt compatible workers into OpenShell. When selected, retain
the stock SDK block or auxiliary-service handler
with `runner_module: "MirrorNeuron.Runner.OpenShell"` and
`artifact_handoff: {"version": "mn.artifact_handoff/v1"}`. Declare the custom
image, domain uploads and scoped network/filesystem policy in the blueprint. The SDK
includes the compiled descriptor automatically, and Core binds its discovery to
the private invocation. The shared integration stages verified inputs into private run storage, transports
nested JSON/byte artifacts and commits outputs before downstream delivery. Domain
hooks keep using `block.store`; no blueprint handoff wrapper is needed. Architecture
Advisor's packet reviewer uses this path. Other worker choices remain unchanged.
SDK file publishers use private logical output storage and typed export manifests;
select `artifact_handoff.export_outputs: true` for Core-owned output-folder
delivery. Required copy failures reject. Optional copy failures remain qualified
and can recover from committed receipts without rerunning domain work.
Deploy matching SDK/Core support together; offline tests do not qualify the live
OpenShell gateway, provider or policy installation.

`tests/test_catalog_block_migration.py` checks all catalog packages, block locks,
custom collaboration graphs and native placement against the pre-migration
contract. Focused suites exercise worker replay, verified publication barriers,
human approvals, child-round tasks, partial service startup and cleanup. Offline
sample fixtures execute compiled worker bindings; they do not replace Core's
scheduler or establish live model, CUDA, camera or robot qualification.

Stage-aware OtterDesk conversation guidance and each blueprint's saved-instruction boundary are documented in [conversation experience](docs/conversation-experience.md). These assets extend the app and packages using the existing runtime contracts.
