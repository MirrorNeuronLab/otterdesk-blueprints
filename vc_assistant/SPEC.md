# VC Assistant SPEC

## What We Want To Achieve

Build a reviewable VC analysis workflow that monitors a folder containing one or more startup document packets, groups those documents by company, performs privacy-safe public research at multiple stages, runs deterministic numerical analysis for each valuation heuristic, audits the results, and writes organized score-only reports.

## Customer Problem

Early-stage startup review is noisy. Pitch decks, notes, founder bios, traction updates, market claims, and technical material arrive in mixed formats. VC analysts need a fast way to compare early opportunities with lightweight heuristics while preserving evidence and avoiding fake precision.

## Design Details

The blueprint is a scheduled batch-style OtterDesk workflow with specialist actors for each major job:

- Intake: `startup_folder_watcher`, `company_packet_grouper`.
- Evidence: `document_evidence_extractor`, `claim_normalizer`.
- Research: `research_planner`, `company_identity_researcher`, `funding_researcher`, `market_comp_researcher`, `traction_verifier`, `rendered_page_researcher`, `research_reconciler`.
- Numerical analysis: `berkus_scorer`, `scorecard_bill_payne_scorer`, `risk_factor_summation_scorer`, `venture_capital_method_scorer`, `first_chicago_scorer`, `comparables_market_multiple_scorer`, `cost_to_duplicate_scorer`.
- Quality and output: `score_consistency_auditor`, `company_report_writer`, `batch_index_writer`.

The workflow groups first-level input subfolders as companies. Loose files are grouped by inferred company names from filenames or document text. Public research is constrained to privacy-safe queries based on company names, product categories, domains, and public claims.

The online research layer uses `w3m_browser_skill` first for lightweight public source collection from the shared DockerWorker image, where the Python skill and `w3m` binary are installed together. It can use `web_browser_skill` as an optional rendered-browser fallback for JavaScript-heavy public sources such as Crunchbase. The workflow records source status, snippets, warnings, and blocked/login/robots outcomes rather than bypassing access controls. Changed company packets, per-company research stages, and numerical method scoring run with bounded parallel workers while outputs remain ordered by stable company slug.

Actor-style LLM analysis uses the local Docker Model Runner default model `small` for ordinary local launches. A `medium` profile is also recorded for deployments that explicitly select a 48GB-or-above runtime node with GPU or integrated-GPU memory, including NVIDIA, Apple, AMD, and DGX Spark / GB10 unified-memory nodes reported by `mn status`. Numerical scoring remains deterministic: formulas, weights, scenario math, missing-evidence status, and audit checks are owned by deterministic workers. Non-substantive records such as research plans, configured references, disabled browser fallback notices, unavailable skills, blocked pages, and failed requests do not create comparable evidence by themselves.

Local LLM calls are deliberately backpressured. The default run serializes Docker Model Runner calls, spaces them slightly, keeps company and research-stage defaults serial, and caps agentic research loops so a scheduled batch does not burst many model calls at once.

## Input

The prototype accepts local startup documents in PDF, TXT, Markdown, JSON, and CSV formats. Text-like files are read directly. PDF files use the shared `llm_ocr_skill` LightOnOCR path for embedded or OCR text extraction. If a PDF startup packet cannot produce usable text, the batch run fails closed instead of creating metadata-only evidence.

## Output: Expected Customer Outcome

Each company gets a dedicated output folder with structured JSON, Markdown, source records, and local evidence records. The report covers:

- Berkus Method
- Scorecard / Bill Payne Method
- Risk Factor Summation Method
- Venture Capital Method
- First Chicago Method
- Comparables / Market Multiple Method
- Cost-to-Duplicate Method

If evidence is missing for a method, the method status is `insufficient_evidence`.

Internal artifacts include `company_work_queue.json`, company fact tables, research ledgers, method-score files, audit findings, research coverage, method coverage, and a run summary.

## Evaluation Criteria

- Company grouping is explainable and stable.
- All seven method sections are present for every company.
- Scores are included where evidence exists.
- Missing evidence is explicit and not hallucinated.
- Public research avoids confidential local excerpts.
- Public research attempts company website, Crunchbase/profile, founder public profile, funding mention, press, competitor, and market-context verification where configured.
- Changed company packets are processed concurrently when `execution.max_company_workers` permits, without changing output ordering.
- Each numerical method emits `status`, `score`, `inputs_used`, `formula_or_weighting`, `assumptions`, `source_refs`, and `warnings`.
- The score consistency auditor flags missing method outputs, invalid scored/null states, unsupported assumptions, and formula coverage gaps.
- Scorecard and Comparables remain `insufficient_evidence` when only default filler values or non-substantive source records exist.
- Outputs are organized into one subfolder per company.
- No investment decision label is emitted.

## Prototype Limits

This is an early heuristic report assistant. Scores are not valuations, investment recommendations, legal advice, or financial advice. Comparable, exit, and rebuild-cost outputs are deliberately conservative when source evidence is thin.

## Upgrade Path To Real Customer Use

Add richer source citation capture, customer-specific scoring weights, authenticated market-data and funding-data connectors, analyst review annotations, historical calibration against partner decisions, and governance controls for confidential data handling.
