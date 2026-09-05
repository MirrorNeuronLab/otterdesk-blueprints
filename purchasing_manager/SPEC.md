# Purchasing Manager SPEC

## Purpose

Provide a source-grounded purchasing workflow for consumer or business
purchases. The workflow turns a plain-text request, supplier evidence,
unfinished public research links, and local evidence into a requirements
matrix, supplier comparison, landed-cost bridge, discounted and risk-adjusted
lifecycle analysis, scenario review, acquisition-method analysis, approval
checklist, evidence-gap list, and review-only recommendation.

## Input Contract

`purchase_request.txt` is the primary request contract. The user can describe
what they want in prose and optionally use labels such as `Purchase type`,
`Budget`, `Location`, `Priorities`, and `Hard constraints`. Public HTTP(S)
links in the note are treated as unverified research leads, not as evidence.
Structured input fields remain optional fallbacks for API-driven runs.
`analysis` carries company planning assumptions separately from sourced facts:
the horizon, discount and tax rates, utilization, energy/fuel, loaded labor,
downtime, maintenance, residual value, and scenario values.

The default bundle-relative input is `@/examples/sample_inputs`; checked-in
overwrite configuration must not replace it with a repository-relative path.
The launcher stages that folder and rewrites the linked runtime input paths.

## Workflow

1. `frame_purchase_request`: normalize the category, technical and commercial constraints, budget, priorities, decision horizon, and approval needs with one bounded `purchase_intake_analyst` LLM call.
2. `build_purchase_evidence`: read approved local quotes and evidence and retrieve checked-in guidance with `purchase_knowledge_retriever`.
3. `compare_purchase_options`: run the source/tool-driven `purchase_market_researcher`, then deterministic TCO modeling plus one bounded interpretation call in `purchase_total_cost_analyst`, followed by deterministic risk flags plus one bounded interpretation call in `purchase_risk_reviewer`. Hard constraints, source timestamps, landed-cost math, discounted cash flow, risk adjustment, EAC, scenario outputs, and acquisition-method gaps remain authoritative.
4. `audit_purchase_recommendation`: have `purchase_recommendation_auditor` deterministically select the eligible ranking and recommendation, then use one bounded LLM call to explain the result, alternatives, and approval conditions without changing them.
5. `publish_purchase_decision_packet`: have `purchase_report_writer` use one bounded LLM call for validated narrative sections, then durably render the JSON and Markdown packet in code with authoritative numerical tables and source references.

The compiler owns step boundaries, routing, joins, and logical completion. The
specialists return bounded coordination results plus artifact references; they
do not address streams or traverse workflow dependencies.

## Supported Categories

- Property and rental property: ownership or lease terms, taxes, insurance, inspections, utilities, deposits, maintenance, and occupancy evidence.
- Cars: identity, title, mileage, recalls, inspection, warranty, financing, insurance, taxes, registration, and maintenance.
- Airline tickets: fare rules, taxes, baggage, seats, changes, cancellation, refunds, schedule, connections, and entry requirements.
- Computers and office equipment: exact observed and quoted configuration, technical fit, purchase availability, hardware lifecycle, fulfillment/deployment, taxes, energy, downtime, residual value, security, warranty, support, supplier terms, and deployment dependencies.
- Any other purchase: identify the category-specific fit, quality, compatibility, lifecycle, policy, provider, safety, privacy, regulatory, logistics, and exit questions before comparing options.

## Research Boundaries

Public research uses sanitized item, location, route, timing, and
non-confidential constraint text only. Supplied links must use public HTTP(S),
must not target local/private addresses, and must not contain credentials or
sensitive query parameters. `web_browser_skill` standard mode owns the unified
source path: it starts with lightweight text extraction and uses its
policy-governed rendered browser only when needed for public JavaScript-heavy
pages. Direct research leads are deduplicated and refreshed before concise
gap-filling discovery queries. Source counts, query counts, page timeouts, total
page work, response size, and per-host delay are explicitly bounded. Login
walls, robots restrictions, CAPTCHAs, rate limits, and access
denials are recorded as source warnings. The workflow never bypasses access
controls and never performs a transaction.

## Persistent job data

Persistent knowledge, RAG storage, and declared state are isolated by stable
`job_id`; two jobs built from this blueprint do not share data. Run retention
and deletion do not clear job data.

## Output Contract

The primary artifact is a `mn.blueprint.purchasing_manager.v1` packet containing the purchase type, item description, recommendation label, confidence, rationale, deterministic evidence, public-source records, RAG citations, supplier or candidate comparisons, landed acquisition cost, financial NPV TCO, risk-adjusted NPV TCO, equivalent annual cost, productive-unit economics, scenario sensitivity, cash/finance/lease status, procurement decision summary, approval checklist, risks, evidence gaps, next steps, and blocked actions. Additive structured fields carry TCO interpretation, risk interpretation, decision analysis, report narrative, and per-phase LLM generation provenance. The Markdown report is a code-rendered, human-readable view of the same evidence and validated narrative.

At most five LLM calls may run per workflow execution, one for each selected
specialist phase. Prompts contain bounded decision packets rather than raw
private document text. Candidate IDs, metric references, and source references
must resolve to deterministic state. Unsupported numerical or reference claims
are rejected section by section. Because `llm.require_live` is false, provider,
timeout, malformed-output, and validation failures preserve the deterministic
packet, set LLM generation status to `completed_with_fallback`, and add a
visible report warning.

Recommendation labels are `buy`, `consider`, `wait`, `avoid`, and `insufficient_evidence`. They are decision-support labels, not professional legal, financial, travel, automotive, or real-estate advice.

## Evaluation

- Category-specific inputs normalize correctly.
- Plain-text requests override generic structured fallbacks and preserve their
  source reference.
- Safe public links become bounded research leads; private or credential-bearing
  links are rejected before browser use.
- Deterministic prices, dates, fee fields, hashes, and source statuses are not overwritten by LLM output.
- LLM narrative cannot change hard gates, eligible candidates, ranking,
  recommendation label, confidence cap, or any lifecycle calculation.
- A run makes no more than five bounded LLM calls and records prompt hashes,
  provider/model metadata, usage, validation status, and fallback reasons
  without persisting raw prompts.
- Unknown candidate, metric, and source references and unsupported numerical
  claims fall back visibly while the deterministic report remains usable.
- Local RAG returns citations from checked-in knowledge and approved user documents.
- Public source records retain URLs, timestamps, snippets, skills, status, and warnings.
- Missing, stale, conflicting, and blocked evidence is explicit.
- Offline verification runs are deterministic and write the complete output bundle without turning unavailable public data into facts.
- No transactional action is emitted or executed.
- The bundled procurement packet uses URL-backed public observations, rejects options that fail availability, technical, warranty, or landed-budget gates, ranks eligible options by risk-adjusted NPV TCO, reports EAC and scenario range, marks finance/lease analysis incomplete without real terms, and preserves source-refresh, quote, deployment, assumption, and approval gaps separately.

## Persistent Job response service

The stable job exposes bounded role, safe configuration, schedule, lifecycle,
and latest-run context through the top-level Job response service. It requires no
active workflow and cannot research, buy, book, configure, or start work.

## Blueprint package format

This blueprint uses the canonical blueprint/v1 format in both folders and ZIPs.
`manifest.json` contains identity, semantic release version, and document references.
`workflow.json` owns logical topology and policies; `execution.json` owns workers,
resources, and services; `contracts.json` owns input/output and artifact contracts.
Platform descriptors live in `extensions/`, package requirements in
`dependencies.json` when present, and operator defaults in `config/default.json`.
The SDK reads these documents together and compiles the Core execution artifact.
A ZIP contains the same files as the folder. Local overrides and invocation
configuration are resolved by the SDK before launch.
