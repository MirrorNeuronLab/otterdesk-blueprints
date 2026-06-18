# Property Deal Research Assistant

`Blueprint ID:` `property_deal_research_assistant`
`Category:` `Finance`

A property deal research co-worker for comparing real-estate opportunities. Give it a target ZIP code, price ceiling, deal history, memory policy, optional broker notes, financing constraints, and an input folder for supporting files; it researches and scores opportunities, explains tradeoffs, and writes ranked review artifacts to the output folder.

## What It Does

This blueprint compares acquisition opportunities against buyer criteria, deal history, financing assumptions, and diligence questions. It preserves source-grounded reasoning for rent upside, renovation risk, debt-service sensitivity, seller/broker claims, and document gaps before writing a review-only acquisition memo.

The default sample pack includes a synthetic small-multifamily watchlist in `examples/sample_inputs/sample_deal_watchlist.json`. Use it for local demos, then replace it with customer-approved deal sheets, broker notes, rent rolls, lender terms, inspections, and public-record exports.

## Quick Start

Run from the catalog:

```bash
mn run property_deal_research_assistant
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

- `manifest.json`: graph shape, entrypoints, runtime metadata, runners, services, and environment access.
- `config/default.json`: default launch configuration, live Docker Model Runner profile, and mock/sample input settings.
- `config/overwrite.json`: optional local overrides layered on defaults.
- `payloads/`: worker scripts, policies, fixtures, prompts, and support files used by this blueprint.
- `knowledge/product_readiness_retrieval.md`: RAG guidance for ranking evidence, diligence blockers, and review-only outputs.

## Outputs

Most runs write artifacts under `~/.mn/runs/<run_id>/`. Common files include
`events.jsonl`, `result.json`, `final_artifact.json`, worker logs, and generated
reports when the blueprint produces them.

The final artifact should rank opportunities, list assumptions, name source gaps, and recommend diligence actions rather than executable acquisition decisions.

## Safety Checklist

- Review `manifest.json` and `payloads/` before running with real data.
- Check `pass_env`, provider credentials, Slack/email/web adapters, and any shell or OpenShell runners.
- Start with mock, dry-run, or quick-test configuration before live external integrations.
- Keep local customer overrides out of committed defaults.

## Local Documentation

- [SPEC](SPEC.md)
- [TERM](TERM.md)
- [License](LICENSE.md)

- [Manifest](manifest.json)
- [Default config](config/default.json)

## Validation

Run repository-level tests from `otterdesk-blueprints` after changing catalog metadata,
manifest structure, payload behavior, or shared fixtures:

```bash
cd ..
.venv/bin/python -m pytest -q
```
