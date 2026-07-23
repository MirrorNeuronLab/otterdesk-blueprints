# Purchase Research Assistant v2 SPEC

## Purpose

Provide a source-grounded purchase study workflow for any consumer or business purchase. The workflow turns a purchase request plus local evidence into a comparison, risk review, evidence-gap list, and review-only recommendation.

## Workflow

1. `frame_purchase_request`: normalize the category, constraints, budget, and priorities with `purchase_intake_analyst`.
2. `build_purchase_evidence`: read approved local evidence and retrieve checked-in guidance with `purchase_knowledge_retriever`.
3. `compare_purchase_options`: run `purchase_market_researcher`, `purchase_total_cost_analyst`, `purchase_risk_reviewer`, and `purchase_recommendation_auditor` in sequence. Hard constraints and deterministic cost fields remain authoritative.
4. `publish_purchase_decision_packet`: have `purchase_report_writer` durably write the bounded JSON and Markdown packet.

The compiler owns step boundaries, routing, joins, and logical completion. The
specialists return bounded coordination results plus artifact references; they
do not address streams or traverse workflow dependencies.

## Supported Categories

- Property and rental property: ownership or lease terms, taxes, insurance, inspections, utilities, deposits, maintenance, and occupancy evidence.
- Cars: identity, title, mileage, recalls, inspection, warranty, financing, insurance, taxes, registration, and maintenance.
- Airline tickets: fare rules, taxes, baggage, seats, changes, cancellation, refunds, schedule, connections, and entry requirements.
- Any other purchase: identify the category-specific fit, quality, compatibility, lifecycle, policy, provider, safety, privacy, regulatory, logistics, and exit questions before comparing options.

## Research Boundaries

Public research uses sanitized item, location, route, timing, and non-confidential constraint text only. The primary source path is `w3m_browser_skill`; a rendered browser may inspect public JavaScript-heavy pages. Login walls, robots restrictions, CAPTCHAs, rate limits, and access denials are recorded as source warnings. The workflow never bypasses access controls and never performs a transaction.

## Persistent job data

Persistent knowledge, RAG storage, and declared state are isolated by stable
`job_id`; two jobs built from this blueprint do not share data. Run retention
and deletion do not clear job data.

## Output Contract

The primary artifact is a `mn.blueprint.purchase_research.v1` packet containing the purchase type, item description, recommendation label, confidence, rationale, deterministic evidence, public-source records, RAG citations, risks, evidence gaps, next steps, and blocked actions. The Markdown report is a human-readable rendering of the same evidence.

Recommendation labels are `buy`, `consider`, `wait`, `avoid`, and `insufficient_evidence`. They are decision-support labels, not professional legal, financial, travel, automotive, or real-estate advice.

## Evaluation

- Category-specific inputs normalize correctly.
- Deterministic prices, dates, fee fields, hashes, and source statuses are not overwritten by LLM output.
- Local RAG returns citations from checked-in knowledge and approved user documents.
- Public source records retain URLs, timestamps, snippets, skills, status, and warnings.
- Missing, stale, conflicting, and blocked evidence is explicit.
- Fake/offline runs are deterministic and write the complete output bundle.
- No transactional action is emitted or executed.
- The sample comparison rejects candidates that fail hard constraints and preserves known-cost, unknown-cost, and financing gaps separately.
