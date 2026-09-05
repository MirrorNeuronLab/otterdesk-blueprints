# OtterDesk Blueprints

`otterdesk-blueprints` is a self-contained OtterDesk-facing worker blueprint catalog. Each blueprint folder includes
its own manifest, configuration, payloads, README, and user-facing `SPEC.md`.

VC Assistant, Financial Advisor, Legal Assistant, and Research Assistant
use foundational `mn_sdk.llm` calls through blueprint support; they do not
depend on the deprecated LiteLLM communication skill. Their RAG and OCR skills
own model specifications and use the SDK runtime model wrapper, while each
blueprint declares only its product-level behavior and required skills.

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
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements-test.txt
.venv/bin/python -m pytest -q
```

See [Runtime DAG Flow Patterns](DAG_FLOW_PATTERNS.md) for the catalog's
event-driven, fork/join, service, and linear flow contracts.

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

| Blueprint | Category | Purpose |
| --- | --- | --- |
| [`gtm_assistant`](gtm_assistant/README.md) | Business | Turns de-identified customer feedback into activation, retention, product, and lifecycle decisions. |
| [`drug_discovery_research_assistant`](drug_discovery_research_assistant/README.md) | Science | Runs one discovery cycle, evaluates five distinct molecules, writes a review packet to ~/Downloads/{job_name}, and completes. |
| [`research_assistant`](research_assistant/README.md) | Science | A research assistant that combines deterministic evidence and verification stages with an isolated OpenShell worker for autonomous goal refinement, tool-driven exploration, hypothesis generation, and bounded generated-code experiments. |
| [`software_architecture_advisor`](software_architecture_advisor/README.md) | Engineering | An air-gapped, read-only software architecture advisor. Give it a local source folder; it produces evidence-backed architecture analysis and copy-ready improvement prompts without changing code. |
| [`purchasing_manager`](purchasing_manager/README.md) | Finance | A source-grounded purchasing co-worker for heavy-asset decisions. It screens real market options, models landed cost, discounted and risk-adjusted TCO, EAC, unit economics, scenarios, and cash/finance/lease terms, then prepares an approval-ready packet without transacting. |
| [`cctv_operator`](cctv_operator/README.md) | Security | A steerable NVIDIA CCTV co-worker with a self-contained Docker demo stream, CUDA-assisted MJPEG preview, live operator event feed, sparse baseline analysis, event-triggered frame bursts, and durable reviewed-frame artifacts. |
| [`microduck_controller`](microduck_controller/README.md) | Robotics | Lets an OtterDesk user control the live Microduck MuJoCo simulation in ordinary language through bounded MCP actions, deterministic ball navigation, and stoppable continuous free play. |
| [`legal_assistant`](legal_assistant/README.md) | Legal | A review-only legal document co-worker for invoice, bill, and contract review. Put invoices, bills, contracts, clause notes, labels, or supporting files in the input folder; it extracts payable fields, maps contract clauses, compares playbook expectations, flags review issues, and writes a source-grounded review packet to the output folder. |

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

The standard payload layout is consistent across the catalog: `runtime/` contains
the blueprint context adapter, `steps/` contains manifest-facing handlers, and
`agents/` contains domain workers or services. Docker, native-host, OpenShell,
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
