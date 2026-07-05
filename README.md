# OtterDesk Blueprints

`otterdesk-blueprints` is a self-contained OtterDesk-facing worker blueprint catalog. Each blueprint folder includes
its own manifest, configuration, payloads, README, and user-facing `SPEC.md`.

## Quick Start

List available blueprints:

```bash
mn blueprint list
```

Run a catalog blueprint:

```bash
mn run <blueprint_id>
```

Run a checked-in folder directly:

```bash
cd <blueprint_id>
mn run --folder .
```

Run repository tests:

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements-test.txt
.venv/bin/python -m pytest -q
```

The catalog contract tests also expect this repository to live beside the companion
`mn-skills` and `mn-agents` folders because they import shared blueprint support
helpers and render shared agent templates.

## Catalog

| Blueprint | Category | Purpose |
| --- | --- | --- |
| [`drug_discovery_research_assistant`](drug_discovery_research_assistant/README.md) | Science | A research co-worker for early drug-discovery triage. Give it a disease or target profile, screening criteria, optional candidate seeds, literature notes, and an input folder for supporting files; it stages an evidence-backed discovery workflow and writes review-ready candidate summaries, scores, assumptions, risks, and source notes to the output folder. |
| [`generic_customer_service_voice_coworker`](generic_customer_service_voice_coworker/README.md) | Business | A voice customer-service co-worker for a small business demo. Give it the business name, service scope, opening message, escalation rules, editable knowledge text, and optional sample/input folder; it starts a local WebRTC voice experience and writes service status, conversation logs, knowledge snapshots, and handoff-ready run artifacts to the output folder. |
| [`financial_advisor`](financial_advisor/README.md) | Finance | A unified personal financial advisor co-worker. Put bank statements, receipts, bills, income records, W-2s, 1099s, tax-form images with answer files, brokerage statements, portfolio files, and related finance documents in the input folder; it extracts document evidence, captures tax-form OCR fields for review, prepares review-only tax and household finance summaries, runs portfolio risk analysis, and writes integrated advisor reports to the output folder. |
| [`property_deal_research_assistant`](property_deal_research_assistant/README.md) | Finance | A property deal research co-worker for comparing real-estate opportunities. Give it a target ZIP code, price ceiling, deal history, memory policy, optional broker notes, financing constraints, and an input folder for supporting files; it researches and scores opportunities, explains tradeoffs, and writes ranked review artifacts to the output folder. |
| [`vc_assistant`](vc_assistant/README.md) | Finance | A VC analysis co-worker for early startup screening reports. Put pitch decks, memos, financial snippets, company folders, or other startup documents in the input folder; it groups documents by company, performs privacy-safe public research, applies seven VC heuristic scoring methods, audits the math and evidence, and writes score-only per-company reports and batch indexes to the output folder. |
| [`video_watch_assistant`](video_watch_assistant/README.md) | Security | A video-watch co-worker for monitoring an approved local or mapped video stream. Give it the stream source, visual targets, alert policy, and optional input folder assets; it detects configured objects or activities and writes reviewable observations, counts, positions, confidence, and alert status artifacts to the output folder. |
| [`personal_legal_assistant`](personal_legal_assistant/README.md) | Legal | A personal legal document co-worker for invoice, bill, and contract review. Put invoices, bills, contracts, clause notes, labels, or supporting files in the input folder; it extracts payable fields, maps contract clauses, compares playbook expectations, flags review issues, and writes a source-grounded review packet to the output folder. |
| [`medical_deid_record_intake_assistant`](medical_deid_record_intake_assistant/README.md) | Healthcare | A medical de-identification co-worker for privacy review. Put clinical-style PDFs, labels, or bounding-box files in the input folder; it detects PHI/PII, extracts record fields, notes redaction risks, and writes a review-gated de-identification packet with evidence and warnings to the output folder. |

## Folder Contract

Most blueprint folders contain:

| Path | Purpose |
| --- | --- |
| `README.md` | Self-contained quickstart, inspection notes, and validation guidance. |
| `SPEC.md` | User-facing problem, outcome, evaluation criteria, limits, and upgrade path. |
| `TERM.md` | Terms, assumptions, or domain notes when present. |
| `manifest.json` | Workflow contract, workflow steps and transitions, agent communication graph, runtime worker bindings, metadata, runners, services, and environment access. |
| `config/default.json` | Default launch configuration and mock/sample inputs. |
| `config/overwrite.json` | Optional local overrides. Do not commit customer secrets. |
| `payloads/` | Worker code, prompts, policies, fixtures, and support files. |

## Safety Checklist

- Review `manifest.json`, `payloads/`, and `pass_env` before live runs.
- Start with mock, dry-run, or quick-test settings before enabling real external services.
- Keep customer-specific inputs and secrets in local overrides or environment variables.
- Update the local blueprint README and `SPEC.md` when behavior, inputs, outputs, or limits change.
