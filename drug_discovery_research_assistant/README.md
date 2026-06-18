# Drug Discovery Research Assistant

`Blueprint ID:` `drug_discovery_research_assistant`
`Category:` `Science`

A research co-worker for early drug-discovery triage. Give it a disease or target profile, screening criteria, optional candidate seeds, literature notes, and an input folder for supporting files; it stages an evidence-backed discovery workflow and writes review-ready candidate summaries, scores, assumptions, risks, and source notes to the output folder.

## What It Does

This blueprint organizes early discovery hypotheses, target profiles, candidate seed sets, assay plans, and safety filters into a review-only ranking packet. It helps researchers compare evidence quality and next experiments without implying clinical, regulatory, or wet-lab validation.

The default sample pack includes `target_profile.json` and `candidate_seed_set.csv` under `examples/sample_inputs`. They are synthetic inputs for workflow validation; replace them with approved program data before real scientific review.

## Quick Start

Run from the catalog:

```bash
mn run drug_discovery_research_assistant
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
- `knowledge/product_readiness_retrieval.md`: RAG guidance for target fit, candidate ranking, safety filters, evidence gaps, and report boundaries.

## Outputs

Most runs write artifacts under `~/.mn/runs/<run_id>/`. Common files include
`events.jsonl`, `result.json`, `final_artifact.json`, worker logs, and generated
reports when the blueprint produces them.

The final artifact should rank candidates, show evidence and uncertainty, list blockers, and recommend the next non-clinical experiment for human scientific review.

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
