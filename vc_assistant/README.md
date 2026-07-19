# VC Assistant

`Blueprint ID:` `vc_assistant`
`Category:` `Finance`

Checks a local folder of startup documents on each scheduled batch run, builds a company work queue, runs specialist research and deterministic numerical-analysis agents, and writes organized score-only VC reports for human review.

## What It Does

This blueprint is a report-only early diligence assistant. It helps a reviewer inspect one or more startup document packets with a specialist agent crew for grouping, evidence extraction, fact normalization, public research, seven deterministic scoring methods, score auditing, and batch report writing. MirrorNeuron routes each assigned agent through acknowledged Redis Streams while durable evidence and reports remain filesystem artifacts. The workflow uses `manual_recover`: after a runtime interruption, relaunch the blueprint from its durable inputs instead of repeatedly reconstructing the full agent graph from Redis snapshots.

It does not decide whether to invest, pass, watch, or reject. It writes scores, evidence, assumptions, missing-evidence flags, and source references so the user can decide.

All actor-style LLM analysis uses the local Docker Model Runner default model `small` for ordinary local launches. A `medium` profile is also recorded for deployments that explicitly select a 48GB-or-above runtime node with GPU or integrated-GPU memory, including NVIDIA, Apple, AMD, and DGX Spark / GB10 unified-memory nodes reported by `mn status`. Numerical formulas and missing-evidence gates remain deterministic.

PDF startup packets are extracted through the shared `llm_ocr_skill`. TXT, Markdown, JSON, and CSV files are read directly; the skill prepares its private OCR model lazily only when a PDF needs OCR, and PDF files must produce embedded or OCR text for the batch run to continue.

## Online Research Skills

The research phase is configured to use:

- `web_browser_skill` as the single public-browser capability. Standard mode handles discovery, readable-text extraction, retries, throttling, and automatic local engine selection; deep mode uses the constrained `agent-browser` actuator for explicitly rendered profile checks.

The workflow plans privacy-safe searches for company websites, Crunchbase, founder public profiles, funding mentions, competitors, press, and market context. It consumes plain-text results only. Blocked, login-required, CAPTCHA, robots, or rate-limit responses are recorded in `sources.json`; the blueprint does not bypass them.

## Agents And Workflow Steps

Agents and steps are separate concepts:

- An **agent** is a reusable specialist worker with a role and bounded responsibility.
- A **step** is a durable phase in the workflow DAG. It owns its input/output contract and internal collaboration graph.
- `manifest.json` chains logical steps with `needs`; each `run.definition` points to one `payloads/steps` module.
- The compiler expands each step into a generic start boundary, its agent graph, and a generic end boundary.
- A step may invoke one or many agents, and the same agent may be reused with a unique call alias.
- `agents.registry` owns each reusable handler and its immutable parameters; `llm.agents` only configures optional LLM review.
- Agents receive and return route-free SDK messages; the compiled internal graph owns Redis routing, sequencing, fan-out, and fan-in.

| Workflow step | Required agent crew |
| --- | --- |
| `detect_packet_changes` | `startup_folder_watcher` |
| `assemble_company_packets` | `company_packet_grouper` |
| `prepare_company_evidence` | `document_evidence_extractor`, `claim_normalizer` |
| `plan_public_research` | `research_planner` |
| `collect_public_research` | `company_identity_researcher`, `funding_researcher`, `market_comp_researcher`, `traction_verifier`, `rendered_page_researcher` |
| `reconcile_research_evidence` | `research_reconciler` |
| `calculate_valuation_scores` | the seven method-specific scorer agents |
| `audit_valuation_analysis` | `score_consistency_auditor` |
| `write_company_reports` | `company_report_writer` |
| `publish_batch_summary` | `batch_index_writer` |

`prepare_company_evidence` runs extractor → normalizer. Public research and valuation scoring fan out through Redis, then a named generic join waits for every required result. Only the generated step end boundary completes the logical step and publishes its declared output. Messages contain bounded outputs and artifact references; confidential documents, research ledgers, and reports stay in the durable filesystem data plane.

## Code Ownership

- `payloads/steps/` contains only logical step contracts, input/output mappings, and internal collaboration graphs.
- `payloads/agents/` contains executable specialist workers. Each valuation agent has a discoverable module matching its registry ID; for example, `agents/first_chicago_scorer.py` binds the First Chicago worker.
- `payloads/domain/` contains blueprint-specific diligence policy and deterministic behavior. Valuation formulas are split by method under `domain/valuation/`; the First Chicago formula is in `valuation/first_chicago.py`.
- `payloads/runtime/` contains dependency bootstrap and runtime/service preparation only. It must not import agent behavior.
- Shared, domain-neutral mechanisms stay in the SDK, skills, or reusable agent packages. Route-neutral message parsing and artifact references live in `mn_sdk.step_runtime`; durable message-agent replay lives in `prototype_stateful_step_agent`; document hashing, grouping, and common PII redaction live in `document_reading_skill`.

There is intentionally no `payloads/agents/domain.py`. Agents import only the VC domain modules they own, while reusable skills remain independent of VC terminology.

## Quick Start

Run from the catalog:

```bash
mn run vc_assistant
```

Run directly from this folder:

```bash
mn run --folder .
```

Inspect recent run state:

```bash
mn blueprint monitor --follow
```

## Inputs And Configuration

- `document_folder`: folder containing startup documents. Each first-level subfolder is treated as one company; loose files are grouped by inferred company name.
- `output_folder`: folder where per-company analysis folders and root index files are written.
- `monitoring`: bounded single-run scan controls; the runtime scheduler decides when to launch the batch.
- `input_skills.llm_ocr`: shared OCR enablement and document thresholds for PDF startup packets; model details stay in the skill.
- `input_skills.web_browser`: unified public research with lightweight w3m support in the `docker_worker` image and policy-governed agent-browser/Chrome rendering supplied by the selected browser execution environment. The job image does not install Playwright or its Chromium/system dependency bundle.
- `skill_runtime`: shared DockerWorker image settings for skills that need system binaries.
- `execution.max_company_workers`: maximum changed-company packets processed concurrently; defaults to one for local Docker Model Runner stability.
- `backpressure.llm`: serializes and spaces local LLM calls so agentic research does not overwhelm Docker Model Runner.
- Concurrent RAG-consuming workers use stable per-agent Milvus Lite namespaces, so the shared DockerWorker never opens one database file from multiple processes.
- `internet_research`: public verification targets, bounded browser timeouts, Crunchbase/profile URL templates, and explicit deep-render controls.
- `internet_research.max_parallel_research_agents`: maximum research agents running in parallel per changed company.
- `scoring.max_workers`: maximum parallel method scorers per changed company.

## Outputs

Each company receives a subfolder containing:

- `analysis.json`
- `analysis.md`
- `method_scores.json`
- `research_sources.json`
- `sources.json`
- `evidence.json`
- `warnings.json`

The output root also contains `company_index.json`, `company_index.md`, `company_work_queue.json`, `research_coverage.json`, `method_coverage.json`, `run_summary.md`, and internal artifact folders for fact tables, research ledgers, method scores, and audit findings. When rendered browsing runs, `browser_audit.jsonl` and bounded files under `browser_artifacts/` record the actuator trail and captured artifacts.

## Safety Checklist

- Review `config/default.json` before using real startup documents.
- Keep confidential pitch decks, financials, and customer names local.
- Public research queries should use company names, categories, domains, and public claims, not confidential source excerpts.
- Treat scores as heuristic review aids, not investment advice.
- Generic human-control approval actions in platform metadata are workflow controls, not company filter labels or investment decisions.

## Local Documentation

- [SPEC](SPEC.md)
- [TERM](TERM.md)
- [License](LICENSE.md)
- [Manifest](manifest.json)
- [Default config](config/default.json)
- [Startup research playbook](payloads/knowledge/startup_research_playbook.md)

## Validation

Run repository-level tests from `otterdesk-blueprints` after changing catalog metadata, manifest structure, payload behavior, or shared fixtures:

```bash
.venv/bin/python -m pytest -q
```
