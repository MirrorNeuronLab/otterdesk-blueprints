# Purchasing Manager

`Blueprint ID:` `purchasing_manager`
`Category:` `Finance`

Purchasing Manager turns a business purchase request into a source-grounded,
review-only procurement decision packet. It supports property, rentals, cars,
airline tickets, office equipment, software, services, and other custom or
heavy-asset purchases. Put a plain-text request, supplier evidence,
requirements, public links, and supporting documents in the input folder. It
retrieves approved local evidence, performs bounded public research, tests hard
constraints, and writes an approval-ready numerical comparison without
transacting.

The bundled business case sources one supportable local-AI desktop for a Boston
engineering office, with at least 16 GB GPU VRAM, 64 GB RAM, 2 TB storage, a
one-year warranty, current purchase availability, and a $5,000 landed-
acquisition ceiling. Its three time-stamped public supplier observations use
real source URLs and demonstrate source refresh, technical and availability
gates, tax and deployment cost, support exceptions, and approval checks.

## Process and agents

The runtime compiles five logical steps. `frame_purchase_request` runs the
`purchase_intake_analyst`; `build_purchase_evidence` runs the
`purchase_knowledge_retriever`; `compare_purchase_options` runs the market,
total-cost, and risk specialists in order; `audit_purchase_recommendation`
runs the recommendation auditor as an independent logical review; and
`publish_purchase_decision_packet` runs the report writer. Step modules declare
only contracts and collaboration. Each same-named agent module binds one
specialist to its focused implementation under `payloads/domain/`.

Five existing specialists use one bounded LLM call apiece: intake framing,
TCO interpretation, risk interpretation, recommendation explanation, and
report narrative generation. Deterministic code remains authoritative for all
prices, formulas, scenarios, hard gates, candidate eligibility, rankings,
recommendation labels, and confidence caps. The market researcher remains
source/tool-driven, and the knowledge retriever remains deterministic and
RAG-driven. Model output is validated structured JSON; code renders the final
Markdown and visibly falls back to deterministic narrative if a call fails or
returns unsupported candidate, metric, source, or numerical claims.

The bundled `examples/sample_inputs/purchase_request.txt` is the primary sample
request. It contains the business goal, decision owners, technical and
commercial hard constraints, company planning assumptions, and official public
research leads. `observed_ai_systems.json` records three real, URL-backed market
observations. The workflow ranks eligible options on risk-adjusted discounted
TCO after screening landed acquisition cost, availability, specifications, and
warranty. Public listings remain explicitly subject to refresh, written quote,
technical sign-off, and human approval.

## Quick Start

```bash
mn blueprint run --folder purchasing_manager
```

The default user-facing output folder is `~/Downloads/purchasing_manager`. Run artifacts also appear under `~/.mn/runs/<run_id>/`.

## Inputs

- `input_folder`: start with `purchase_request.txt`; describe the purchase in
  plain text and paste any incomplete public research links. Optional TXT,
  Markdown, JSON, CSV, PDF, or image evidence may live beside it.
- `purchase_type`: optional structured fallback; the text request can specify
  or imply `property`, `rental_property`, `car`, `airline_ticket`, `computer`,
  or `custom`.
- `item_description`: optional structured fallback when no plain-text request
  is present.
- `budget`: optional budget or price ceiling.
- `location`, `route`, and `travel_dates`: optional public context.
- `priorities` and `constraints`: optional ranking preferences and must-have requirements.
- `analysis`: horizon, discount rate, tax, utilization, energy/fuel, loaded
  labor, downtime, maintenance, residual value, and low/base/stress assumptions.
- `output_folder`: defaults to `~/Downloads/purchasing_manager`.

## Research and RAG

Checked-in knowledge under `knowledge/` and usable local input documents are
retrieved in an isolated per-run context. `web_browser_skill` opens safe public
HTTP(S) links supplied in the request first. Concise queries derived only from
sanitized purchase details run when those direct sources leave an evidence gap;
page, query, source-count, response-size, and timeout budgets are explicit in
`config/default.json`. Standard mode uses lightweight w3m extraction
and automatically falls through to the policy-governed rendered browser when
needed. Local/private URLs, credential-bearing URLs, raw documents, private
financials, credentials, and contact details are never sent to public research.
The workflow records blocked, login, robots, CAPTCHA, and transient-source
warnings.

## Shared job data

Bundled knowledge seeds the stable job once. Milvus Lite lives under
`databases/rag/`, and durable application state under `state/`. Repeated runs
share those resources while purchase inputs, citations, recommendations, and
outputs remain run-scoped.

## Outputs

The output bundle contains `purchasing_manager.json`,
`purchasing_manager_report.md`, `evidence.json`, `research_sources.json`,
`knowledge_rag.json`, `action_ledger.json`, `artifact_quality.json`, and
`run_health.json`. The packet includes a procurement decision summary, landed-
budget position, candidate-comparison table, financial and risk-adjusted NPV
TCO, equivalent annual cost, productive-hour cost, scenario sensitivity,
cash/finance/lease status, approval checklist, risk flags, evidence gaps, and
source references. It also includes validated `analysis_interpretation`,
`risk_interpretation`, `decision_analysis`, `report_narrative`, and
`llm_generation` provenance. Recommendations are limited to `buy`, `consider`,
`wait`, `avoid`, or `insufficient_evidence`.

The assistant does not buy, book, pay, issue a purchase order, accept a supplier
quote, sign an agreement, submit an offer or application, or contact a seller,
provider, broker, landlord, dealer, or airline. All output requires human review.

## Payload layout

- `payloads/steps/`: the four logical `StepSpec` graphs.
- `payloads/agents/`: seven route-neutral specialist bindings.
- `payloads/domain/inputs.py`, `intake.py`: request and evidence intake.
- `payloads/domain/knowledge.py`, `research.py`: local and public evidence.
- `payloads/domain/comparison.py`: cost, risk, recommendation, and audit policy.
- `payloads/domain/llm_analysis.py`: bounded prompts, structured validation,
  reference controls, usage provenance, and deterministic fallback.
- `payloads/domain/reporting.py`: durable customer artifacts.
- `payloads/domain/composition.py`: local end-to-end sample runner.
- `payloads/domain/runtime_services.py`: runtime context preparation only.
- `payloads/docker_worker/Dockerfile`: shared Python/w3m worker build context
  used by the compiled specialist nodes.

## Persistent conversation

OtterDesk can ask this hired co-worker about its research role, schedule,
latest comparison, or unresolved evidence through the stable Job response service
even when it has never run or is idle. Conversation never starts research or a
transaction.

## Validation

```bash
.venv/bin/python -m pytest -q
```
