# VC Assistant

`Blueprint ID:` `vc_assistant`
`Category:` `Finance`

Checks a local folder of startup documents on each scheduled batch run, builds a company work queue, runs specialist research and deterministic numerical-analysis agents, and writes organized score-only VC reports for human review.

## What It Does

This blueprint is a report-only early diligence assistant. It helps a reviewer inspect one or more startup document packets with specialist agents for grouping, evidence extraction, fact normalization, public research, seven deterministic scoring methods, score auditing, and batch report writing. The local runner uses bounded parallelism for changed company packets, per-company research stages, and method scoring while preserving stable company-slug output order.

It does not decide whether to invest, pass, watch, or reject. It writes scores, evidence, assumptions, missing-evidence flags, and source references so the user can decide.

All actor-style LLM analysis uses the local Docker Model Runner default model `small` for ordinary local launches. A `medium` profile is also recorded for deployments that explicitly select a 48GB-or-above runtime node with GPU or integrated-GPU memory, including NVIDIA, Apple, AMD, and DGX Spark / GB10 unified-memory nodes reported by `mn status`. Numerical formulas and missing-evidence gates remain deterministic.

PDF startup packets are extracted through the shared `llm_ocr_skill` LightOnOCR path. TXT, Markdown, JSON, and CSV files are read directly; PDF files must produce embedded or OCR text for the batch run to continue.

## Online Research Skills

The research phase is configured to use:

- `w3m_browser_skill` for lightweight text-browser research over public sources, installed with the `w3m` binary inside the shared DockerWorker image.
- `web_browser_skill` as an optional Playwright fallback for JavaScript-rendered public pages such as Crunchbase profiles.

The workflow plans privacy-safe searches for company websites, Crunchbase, founder public profiles, funding mentions, competitors, press, and market context. Blocked, login-required, CAPTCHA, robots, or rate-limit responses are recorded in `sources.json`; the blueprint does not bypass them.

## Workflow Shape

The batch workflow uses a static DAG with fanout/fan-in stages:

- Intake and grouping: `startup_folder_watcher`, `company_packet_grouper`.
- Evidence normalization: `document_evidence_extractor`, `claim_normalizer`.
- Research planning and parallel research: `research_planner`, `company_identity_researcher`, `funding_researcher`, `market_comp_researcher`, `traction_verifier`, `rendered_page_researcher`.
- Research merge: `research_reconciler`.
- Parallel numerical scoring: one scorer for each of the seven requested methods.
- Quality and output: `score_consistency_auditor`, `company_report_writer`, `batch_index_writer`.

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
- `input_skills.llm_ocr`: shared local LightOnOCR OCR settings for PDF startup packets.
- `input_skills.w3m_browser`: public text-browser research provided by the `document_workflow/docker_worker` image.
- `skill_runtime`: shared DockerWorker image settings for skills that need system binaries.
- `execution.max_company_workers`: maximum changed-company packets processed concurrently; defaults to one for local Docker Model Runner stability.
- `backpressure.llm`: serializes and spaces local LLM calls so agentic research does not overwhelm Docker Model Runner.
- `internet_research`: public verification targets, browser-skill settings, Crunchbase/profile URL templates, and rendered-browser fallback controls.
- `internet_research.max_stage_workers`: maximum parallel research stages per changed company.
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

The output root also contains `company_index.json`, `company_index.md`, `company_work_queue.json`, `research_coverage.json`, `method_coverage.json`, `run_summary.md`, and internal artifact folders for fact tables, research ledgers, method scores, and audit findings.

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
