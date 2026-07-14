# Purchase Research Assistant

`Blueprint ID:` `purchase_research_assistant`  
`Category:` `Finance`

Purchase Research Assistant studies any purchase—from property, rentals, cars, and airline tickets to equipment, services, subscriptions, software, and other custom goods. Give it a purchase type, item or trip description, budget, priorities, constraints, and an input folder. It uses the portable local DMR profile, retrieves local guidance and approved user evidence, performs bounded public research, explains tradeoffs, and writes a review-only recommendation.

The bundled sample goal is to find one single-family house with at least 3 bedrooms in ZIP code 03755. No budget is assumed; the assistant should return one source-grounded candidate or `insufficient_evidence` when public listing evidence cannot be verified.

## Quick Start

```bash
mn run purchase_research_assistant
```

The default user-facing output folder is `~/Downloads/purchase_research_assistant`. Run artifacts also appear under `~/.mn/runs/<run_id>/`.

## Inputs

- `purchase_type`: `property`, `rental_property`, `car`, `airline_ticket`, or `custom` for any other good, service, subscription, or commitment.
- `item_description`: item, listing, vehicle, route, or trip being studied.
- `budget`: optional budget or price ceiling.
- `location`, `route`, and `travel_dates`: optional public context.
- `priorities` and `constraints`: optional ranking preferences and must-have requirements.
- `input_folder`: local TXT, Markdown, JSON, CSV, PDF, or image evidence.
- `output_folder`: defaults to `~/Downloads/purchase_research_assistant`.

## Research and RAG

Checked-in knowledge under `knowledge/` and usable local input documents are retrieved in an isolated per-run context. Public queries are derived only from sanitized purchase details; raw documents, private financials, credentials, and contact details are never sent to public research. The workflow uses `w3m_browser_skill` first and an optional rendered-browser fallback, recording blocked, login, robots, CAPTCHA, and transient-source warnings.

## Outputs

The output bundle contains `purchase_research.json`, `purchase_research_report.md`, `evidence.json`, `research_sources.json`, `knowledge_rag.json`, `action_ledger.json`, `artifact_quality.json`, and `run_health.json`. Recommendations are limited to `buy`, `consider`, `wait`, `avoid`, or `insufficient_evidence`.

The assistant does not buy, book, pay, submit an offer or application, or contact a seller, provider, broker, landlord, dealer, or airline. All output requires human review.

## Validation

```bash
.venv/bin/python -m pytest -q
```
