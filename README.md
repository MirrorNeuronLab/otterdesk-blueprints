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
python3 -m pytest -q
```

## Catalog

| Blueprint | Category | Purpose |
| --- | --- | --- |
| [`drug_discovery_research_assistant`](drug_discovery_research_assistant/README.md) | Science | Helps run a reviewable discovery workflow that proposes, filters, and evaluates drug candidates across repeated research stages. |
| [`personal_income_tax_expert`](personal_income_tax_expert/README.md) | Finance | Runs an LLM-assisted tax preparation team over local tax documents, builds draft Form 1040 workpapers, audits the packet, and writes JSON, Markdown, and PDF review outputs. |
| [`portfolio_risk_review_assistant`](portfolio_risk_review_assistant/README.md) | Finance | Stress-tests a portfolio against market crashes, rate shocks, and liquidity pressure, then explains risks and possible rebalancing options in plain language. |
| [`property_deal_research_assistant`](property_deal_research_assistant/README.md) | Finance | Reviews ZIP-code history, broker notes, financing constraints, and deal memory to rank property opportunities and explain which ones deserve attention. |
| [`video_watch_assistant`](video_watch_assistant/README.md) | Security | Watches an approved video stream, detects configured visual targets, and reports count, label, category, color, position, activity, and alert status for review. |

## Folder Contract

Most blueprint folders contain:

| Path | Purpose |
| --- | --- |
| `README.md` | Self-contained quickstart, inspection notes, and validation guidance. |
| `SPEC.md` | User-facing problem, outcome, evaluation criteria, limits, and upgrade path. |
| `TERM.md` | Terms, assumptions, or domain notes when present. |
| `manifest.json` | Workflow contract, flow steps, runtime worker bindings, compatibility graph, metadata, runners, services, and environment access. |
| `config/default.json` | Default launch configuration and mock/sample inputs. |
| `config/overwrite.json` | Optional local overrides. Do not commit customer secrets. |
| `payloads/` | Worker code, prompts, policies, fixtures, and support files. |

## Safety Checklist

- Review `manifest.json`, `payloads/`, and `pass_env` before live runs.
- Start with mock, dry-run, or quick-test settings before enabling real external services.
- Keep customer-specific inputs and secrets in local overrides or environment variables.
- Update the local blueprint README and `SPEC.md` when behavior, inputs, outputs, or limits change.
