# Portfolio Risk Review Assistant

`Blueprint ID:` `portfolio_risk_review_assistant`
`Category:` `Finance`

Stress-tests a portfolio against market crashes, rate shocks, and liquidity pressure, then explains risks and possible rebalancing options in plain language.

## What It Does

This folder is a self-contained MirrorNeuron blueprint. It defines the runtime
manifest, default configuration, payload code, local documentation, and any
fixtures needed to review or run the workflow from this checkout.

## Quick Start

Run from the catalog:

```bash
mn run portfolio_risk_review_assistant
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
- `config/default.json`: default launch configuration and mock/sample input settings.
- `config/overwrite.json`: optional local overrides layered on defaults.
- `payloads/`: worker scripts, policies, fixtures, prompts, and support files used by this blueprint.

## Outputs

Most runs write artifacts under `~/.mn/runs/<run_id>/`. Common files include
`events.jsonl`, `result.json`, `final_artifact.json`, worker logs, and generated
reports when the blueprint produces them.

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
python3 -m pytest -q
```
