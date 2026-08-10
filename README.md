# OtterDesk Blueprints

`otterdesk-blueprints` is a self-contained OtterDesk-facing worker blueprint catalog. Each blueprint folder includes
its own manifest, configuration, payloads, README, and user-facing `SPEC.md`.

VC Assistant, Financial Advisor, Legal Assistant, and Research Co-Scientist
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

The catalog contract tests also expect this repository to live beside the companion
`mn-skills` and `mn-agents` folders because they import shared blueprint support
helpers and render shared agent templates.

## Catalog

| Blueprint | Category | Purpose |
| --- | --- | --- |
| [`growth_partnerships_coworker`](growth_partnerships_coworker/README.md) | Business | Finds qualified demand and partnerships, then connects channel evidence to Finance, Lifecycle, Quality & Safety, and Content handoffs. |
| [`business_finance_coworker`](business_finance_coworker/README.md) | Business | Calculates unit economics, break-even scale, cash guardrails, and cross-functional evidence gaps. |
| [`learning_quality_safety_coworker`](learning_quality_safety_coworker/README.md) | Business | Gates objectives and claims with PASS/REVISE/BLOCK decisions and supplies approved boundaries to peer roles. |
| [`content_studio_coworker`](content_studio_coworker/README.md) | Business | Converts approved briefs into small, versioned release candidates while tracking review quality, reuse, and cost. |
| [`gtm_assistant`](gtm_assistant/README.md) | Business | Turns de-identified customer feedback into activation, retention, product, and lifecycle decisions. |
| [`drug_discovery_research_assistant`](drug_discovery_research_assistant/README.md) | Science | A continuously running drug-discovery research service. Give it a disease or target profile, screening criteria, optional candidate seeds, literature notes, and an input folder; it uses BioTarget and the custom homerquan/DrugClip text-to-molecular-graph model for continuous candidate generation, folding, evaluation, and review-only cycle reports until manually stopped. |
| [`research_coscientist`](research_coscientist/README.md) | Science | A research co-scientist that combines deterministic evidence and verification stages with an isolated OpenShell worker for autonomous goal refinement, tool-driven exploration, hypothesis generation, and bounded generated-code experiments. |
| [`generic_customer_service_voice_coworker`](generic_customer_service_voice_coworker/README.md) | Business | A voice customer-service co-worker for a small business demo. Give it the business name, service scope, opening message, escalation rules, editable knowledge text, and optional sample/input folder; it starts a local WebRTC voice experience and writes service status, conversation logs, knowledge snapshots, and handoff-ready run artifacts to the output folder. |
| [`financial_advisor`](financial_advisor/README.md) | Finance | A unified personal financial advisor co-worker. Put bank statements, receipts, bills, income records, W-2s, 1099s, tax-form images with answer files, brokerage statements, portfolio files, and related finance documents in the input folder; it extracts document evidence, captures tax-form OCR fields for review, prepares review-only tax and household finance summaries, runs portfolio risk analysis, and writes integrated advisor reports to the output folder. |
| [`purchase_research_assistant`](purchase_research_assistant/README.md) | Finance | A purchase research co-worker for property, rental property, cars, airline tickets, and custom purchases. Put a plain-text note describing what you want to buy in the input folder, plus unfinished research, public links, or supporting evidence; it performs bounded research and writes a review-ready recommendation. |
| [`vc_assistant`](vc_assistant/README.md) | Finance | A VC analysis co-worker for early startup screening reports. Put pitch decks, memos, financial snippets, company folders, or other startup documents in the input folder; it groups documents by company, performs privacy-safe public research, applies seven VC heuristic scoring methods, audits the math and evidence, and writes score-only per-company reports and batch indexes to the output folder. |
| [`cctv_operator`](cctv_operator/README.md) | Security | A steerable NVIDIA CCTV co-worker with browser preview, sparse baseline analysis, event-triggered frame bursts, and durable reviewed-frame artifacts. |
| [`legal_assistant`](legal_assistant/README.md) | Legal | A review-only legal document co-worker for invoice, bill, and contract review. Put invoices, bills, contracts, clause notes, labels, or supporting files in the input folder; it extracts payable fields, maps contract clauses, compares playbook expectations, flags review issues, and writes a source-grounded review packet to the output folder. |

## Folder Contract

Most blueprint folders contain:

| Path | Purpose |
| --- | --- |
| `README.md` | Self-contained quickstart, inspection notes, and validation guidance. |
| `SPEC.md` | User-facing problem, outcome, evaluation criteria, limits, and upgrade path. |
| `TERM.md` | Terms, assumptions, or domain notes when present. |
| `manifest.json` | Readable `mn.workflow.source/v2` DAG: direct `needs`, module handlers or agent assignments, control policy, contracts, and runtime requirements. The SDK expands it for Core. |
| `config/default.json` | Default launch configuration and mock/sample inputs. |
| `config/overwrite.json` | Optional local overrides. Do not commit customer secrets. |
| `payloads/` | Worker code, prompts, policies, fixtures, and support files. |

Blueprints that retain knowledge, RAG, or application state across executions
declare `metadata.job_data.resources` in `manifest.json`. Core creates one
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
Keep DAG topology in the manifest rather than duplicating it in blueprint-local
dispatch code or configuration handoff lists.

## Safety Checklist

- Review `manifest.json`, `payloads/`, and `pass_env` before live runs.
- Start with mock, dry-run, or quick-test settings before enabling real external services.
- Keep customer-specific inputs and secrets in local overrides or environment variables.
- Update the local blueprint README and `SPEC.md` when behavior, inputs, outputs, or limits change.
- Declare durable resources by logical name, validated relative path, access
  mode, and optional `@/` bundle seed. Never declare or accept a host path.
