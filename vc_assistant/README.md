# VC Assistant

`Blueprint ID:` `vc_assistant`
`Category:` `Finance`

Monitors a local folder of startup documents, groups files by company, researches public context, applies seven early VC heuristic analysis methods, and writes organized score-only reports for human review.

## What It Does

This blueprint is a report-only early diligence assistant. It helps a reviewer inspect one or more startup document packets with Berkus, Scorecard / Bill Payne, Risk Factor Summation, Venture Capital, First Chicago, Comparables / Market Multiple, and Cost-to-Duplicate methods.

It does not decide whether to invest, pass, watch, or reject. It writes scores, evidence, assumptions, missing-evidence flags, and source references so the user can decide.

## Online Research Skills

The research phase is configured to use:

- `w3m_browser_skill` for lightweight text-browser research over public sources.
- `web_browser_skill` as an optional Playwright fallback for JavaScript-rendered public pages such as Crunchbase profiles.

The workflow plans privacy-safe searches for company websites, Crunchbase, founder public profiles, funding mentions, competitors, press, and market context. Blocked, login-required, CAPTCHA, robots, or rate-limit responses are recorded in `sources.json`; the blueprint does not bypass them.

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
- `monitoring`: folder polling controls, including bounded `max_cycles` for tests and demos.
- `internet_research`: public verification targets, browser-skill settings, Crunchbase/profile URL templates, and rendered-browser fallback controls.

## Outputs

Each company receives a subfolder containing:

- `analysis.json`
- `analysis.md`
- `sources.json`
- `evidence.json`

The output root also contains `company_index.json` and `company_index.md`.

## Safety Checklist

- Review `config/default.json` before using real startup documents.
- Keep confidential pitch decks, financials, and customer names local.
- Public research queries should use company names, categories, domains, and public claims, not confidential source excerpts.
- Treat scores as heuristic review aids, not investment advice.

## Local Documentation

- [SPEC](SPEC.md)
- [TERM](TERM.md)
- [License](LICENSE.md)
- [Manifest](manifest.json)
- [Default config](config/default.json)
- [Startup research playbook](knowledge/startup_research_playbook.md)

## Validation

Run repository-level tests from `otterdesk-blueprints` after changing catalog metadata, manifest structure, payload behavior, or shared fixtures:

```bash
.venv/bin/python -m pytest -q
```
