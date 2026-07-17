# VC Assistant SPEC

## What We Want To Achieve

Build a reviewable VC analysis workflow that monitors a folder containing one or more startup document packets, groups those documents by company, coordinates a reusable specialist-agent crew through explicit DAG steps, performs privacy-safe public research, runs deterministic numerical analysis for each valuation heuristic, audits the results, and writes organized score-only reports.

## Customer Problem

Early-stage startup review is noisy. Pitch decks, notes, founder bios, traction updates, market claims, and technical material arrive in mixed formats. VC analysts need a fast way to compare early opportunities with lightweight heuristics while preserving evidence and avoiding fake precision.

## Design Details

The blueprint is a scheduled batch-style OtterDesk workflow. Agents are reusable specialist workers; steps are durable phases in the workflow DAG. Step ids use action phrases, agent ids use role names, and the two namespaces must remain disjoint.

Each manifest step references a `payloads/steps` module through `run.definition`. That module declares the step's input contract, output contract, and internal `StepSpec` collaboration graph. `agents.registry` defines handlers and immutable handler parameters independently from optional `llm.agents` review configuration. An agent may be reused by multiple steps or calls; every compiled call receives a unique invocation id derived from its step and call alias.

The durable data plane is the run filesystem. The live message plane is acknowledged Redis Streams. Agent handlers use the route-free SDK `receive_input` and `send_output` functions. The workflow DAG contains only logical step dependencies; each compiled step contains a generated source boundary, its internal agent graph, and a generated sink boundary. The internal graph owns routing, fan-out, fan-in, retries, ACKs, deduplication, and dead-letter behavior. `prepare_company_evidence` runs extractor → normalizer, while research and scoring calls run in parallel and join before the sink completes the logical step.

Production code follows a strict ownership boundary. `payloads/steps` owns orchestration declarations, `payloads/agents` owns executable worker entrypoints, `payloads/domain` owns VC-specific evidence/research/valuation/report policy, and `payloads/runtime` owns runtime context and shared-service preparation. Domain-neutral message envelopes, artifact references, durable replay, document intake utilities, and control agents belong to the SDK, reusable agents, and skills. No aggregate `agents/domain.py` compatibility module is permitted.

Every scorer registry ID resolves to a same-named agent module. The shared scorer executor handles durable queue mechanics, while deterministic formulas remain individually inspectable under `domain/valuation` (`first_chicago.py`, `berkus.py`, `scorecard.py`, and the other method modules).

| DAG step | Required agents |
| --- | --- |
| `detect_packet_changes` | `startup_folder_watcher` |
| `assemble_company_packets` | `company_packet_grouper` |
| `prepare_company_evidence` | `document_evidence_extractor`, `claim_normalizer` |
| `plan_public_research` | `research_planner` |
| `collect_public_research` | `company_identity_researcher`, `funding_researcher`, `market_comp_researcher`, `traction_verifier`, `rendered_page_researcher` |
| `reconcile_research_evidence` | `research_reconciler` |
| `calculate_valuation_scores` | `berkus_scorer`, `scorecard_bill_payne_scorer`, `risk_factor_summation_scorer`, `venture_capital_method_scorer`, `first_chicago_scorer`, `comparables_market_multiple_scorer`, `cost_to_duplicate_scorer` |
| `audit_valuation_analysis` | `score_consistency_auditor` |
| `write_company_reports` | `company_report_writer` |
| `publish_batch_summary` | `batch_index_writer` |

The workflow groups first-level input subfolders as companies. Loose files are grouped by inferred company names from filenames or document text. Public research is constrained to privacy-safe queries based on company names, product categories, domains, and public claims.

The online research layer uses `web_browser_skill` as its only browser capability. Standard mode performs provider discovery, readable plain-text extraction, bounded retries, throttling, and adaptive local engine selection; explicit deep mode renders JavaScript-heavy public sources such as Crunchbase. The workflow records source status, snippets, warnings, and blocked/login/robots outcomes rather than bypassing access controls. Changed company packets, per-company research agents, and numerical method scorers run with bounded parallel workers while outputs remain ordered by stable company slug.

Actor-style LLM analysis uses the local Docker Model Runner default model `small` for ordinary local launches. A `medium` profile is also recorded for deployments that explicitly select a 48GB-or-above runtime node with GPU or integrated-GPU memory, including NVIDIA, Apple, AMD, and DGX Spark / GB10 unified-memory nodes reported by `mn status`. Numerical scoring remains deterministic: formulas, weights, scenario math, missing-evidence status, and audit checks are owned by deterministic workers. Non-substantive records such as research plans, configured references, disabled browser fallback notices, unavailable skills, blocked pages, and failed requests do not create comparable evidence by themselves.

Local LLM calls are deliberately backpressured. The default run serializes Docker Model Runner calls, spaces them slightly, keeps company and research-agent defaults serial, and caps agentic research loops so a scheduled batch does not burst many model calls at once.

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
- Workflow step ids and agent ids remain disjoint.
- Every step definition references one or more valid registry agents and declares its input and output mappings.
- Multi-agent research and scoring crews join before their containing step completes.
- Agent messages contain bounded results and artifact references rather than confidential documents or large ledgers.
- `payloads/runtime/runtime.py` remains below 500 lines and contains only runtime context, configuration, service preparation, observability, and lifecycle persistence.
- `payloads/agents/domain.py` does not exist, agent modules do not import it, and no VC domain module grows beyond the architecture size guard.
- Every valuation scorer registry entry resolves to a same-named agent module and an individually owned formula module.
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
