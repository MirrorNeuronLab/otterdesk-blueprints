# Purchase Research Assistant v2 SPEC

## Purpose

Provide a source-grounded purchase study workflow for any consumer or business purchase. The workflow turns a purchase request plus local evidence into a comparison, risk review, evidence-gap list, and review-only recommendation.

## Workflow

1. Normalize the purchase category and user request.
2. Read approved local evidence using direct text extraction or the shared OCR skill.
3. Retrieve relevant checked-in guidance and user-document evidence through isolated per-run RAG.
4. Use the portable local DMR profile for intake and research planning, then collect privacy-safe public price, availability, fee, policy, and risk evidence.
5. Run bounded specialists for price, total cost, policies, risks, alternatives, recommendation, audit, and reporting.
6. Preserve deterministic fields, source references, retrieval timestamps, warnings, and human review boundaries.

## Supported Categories

- Property and rental property: ownership or lease terms, taxes, insurance, inspections, utilities, deposits, maintenance, and occupancy evidence.
- Cars: identity, title, mileage, recalls, inspection, warranty, financing, insurance, taxes, registration, and maintenance.
- Airline tickets: fare rules, taxes, baggage, seats, changes, cancellation, refunds, schedule, connections, and entry requirements.
- Any other purchase: identify the category-specific fit, quality, compatibility, lifecycle, policy, provider, safety, privacy, regulatory, logistics, and exit questions before comparing options.

## Research Boundaries

Public research uses sanitized item, location, route, timing, and non-confidential constraint text only. The primary source path is `w3m_browser_skill`; a rendered browser may inspect public JavaScript-heavy pages. Login walls, robots restrictions, CAPTCHAs, rate limits, and access denials are recorded as source warnings. The workflow never bypasses access controls and never performs a transaction.

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
