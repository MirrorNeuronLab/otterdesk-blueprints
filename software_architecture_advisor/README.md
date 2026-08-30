# Software Architecture Advisor

`Blueprint ID:` `software_architecture_advisor`  
`Category:` `Engineering`

Software Architecture Advisor is an air-gapped, read-only architecture review
for a single software repository. It inventories the staged source, builds a
syntax/symbol and dependency fact database, reconstructs state, trust, test,
and deployment boundaries, triangulates change-risk hypotheses, and produces
prioritized improvement prompts for an AI coding agent. Eight required,
specialist passes through the runtime-selected `default` local model perform
investigation planning, reconstruction, cross-cutting analysis, finding
synthesis, adversarial review, prompt authoring, report synthesis, and final
audit.
It never modifies, executes, builds, tests, installs, or uploads the target
project.

## Requirements

This blueprint requires at least **48 GB of host memory** and the runtime's
runtime-prepared `default` local model. The platform selects the concrete larger
model and injects the selected node's reachable model gateway and lazy
model-control service into Docker workers. The blueprint never hardcodes a node,
model ID, or direct model-runner endpoint and never downloads a model itself.
Normal runs require real provider responses and fail if any pass falls back.

## Input

Provide exactly one source locator:

- `input_folder`: a local folder containing the source snapshot to inspect.
- `github_repo_url`: an HTTPS GitHub repository URL. OtterDesk's connected
  intake service clones a shallow snapshot before the air-gapped job begins and
  mounts that snapshot as `input_folder`. The job itself has no network egress.

`branch` is optional for the GitHub intake request. `analysis_focus` can call
out a concern such as modularity, reliability, migration risk, or data
ownership. The input source is treated as untrusted data; embedded instructions
in source comments or documentation never override this blueprint's policy.

The bundled default remains the small offline fixture at
`@/examples/sample_inputs`, and it is included in every worker payload, so
`mn blueprint run software_architecture_advisor` works without network access
or a cross-node input mount. Its
[`ARCHMIND_GITHUB_REPOSITORY.txt`](examples/sample_inputs/ARCHMIND_GITHUB_REPOSITORY.txt)
file records `https://github.com/homerquan/Archmind` as the default repository
for a platform-owned GitHub pre-staging request. It is a reference only: the
air-gapped advisor does not fetch it. After intake stages a snapshot, provide
that staged directory as `input_folder` together with the repository URL.

## Quick start

Analyze the included toy source snapshot:

```bash
mn blueprint run software_architecture_advisor
```

For a local codebase, supply an absolute path:

```json
{
  "input_folder": "/work/acme-service",
  "analysis_focus": ["module boundaries", "testability"]
}
```

For GitHub, submit the URL to the intake adapter, then wait for the source
snapshot to be staged before the isolated review starts:

```json
{
  "github_repo_url": "https://github.com/homerquan/Archmind",
  "branch": "main"
}
```

## What it produces

The output folder contains:

- `architecture_assessment.json` — machine-readable findings, evidence,
  confidence, limitations, and priorities.
- `architecture_report.md` — a reviewer-friendly analysis of the source
  snapshot and its highest-leverage improvements.
- `improvement_prompts.md` and `improvement_prompts.json` — copy-ready,
  scoped prompts for Codex or another coding agent. Every prompt includes
  evidence, constraints, acceptance criteria, and verification expectations.
- `architecture_graph.json`, `source_inventory.json`, and
  `analysis_metrics.json` — inspectable static-analysis evidence.
- `evidence/` — repository profile, symbol index, normalized fact database,
  state/trust/test/deployment models, optional pre-staged Git-history evidence,
  architecture reconstruction, adversarial review, prioritized findings, and
  `llm_analysis.json` with the validated output and usage provenance for all
  eight model stages.
- `llm_trace.jsonl` — metadata-only provider/model/latency/token/retry/fallback
  records. It excludes prompts, source excerpts, credentials, and full model
  responses.
- `architecture-report/` — numbered reviewer views for repository structure,
  dependencies, hotspots, state, trust boundaries, tests, and migration order.
- `codex-prompts/` — one standalone prompt per prioritized finding.

Prompts recommend changes but never perform them. They explicitly instruct a
coding agent to inspect the cited paths, preserve behavior, add or update tests,
and stop for human direction when the evidence is insufficient.

## Analysis process

1. Validate the source locator and record whether the snapshot was local or
   pre-staged from GitHub.
2. Inventory only allowed source and manifest files; skip secrets, vendored
   trees, build artifacts, and oversized files.
3. Build an import graph, syntax/symbol index, repository profile, state and
   trust candidates, direct test links, deployment declarations, and fused
   structural hotspots.
4. Normalize observations into stable fact IDs. HIGH findings require at least
   two independent evidence types; missing history, runtime, compiler, or
   executed-test evidence remains explicitly unavailable.
5. Run required model passes for intake planning, component reconstruction,
   cross-cutting mapping, grounded finding synthesis, and adversarial review.
6. Rank surviving findings by risk, leverage, evidence confidence, and migration
   cost; present alternatives instead of a single dogmatic refactor.
7. Generate standalone prompts with architecture intent, fact IDs,
   counter-evidence checks, options, migration order, tests, acceptance criteria,
   and rollback considerations.
8. Draft model-written analytical narrative, audit the complete package with the
   final model pass and deterministic checks, then publish without changing the
   source folder.

## Air-gap and privacy

The analysis environment has `network.egress: forbidden`. The bundled
`software_architecture_graph_skill` uses only the Python standard library and
works on files in the staged source root. The local model is called through a
selected node's local model gateway. Source code, secrets, and reports are not
sent to external services. Bounded source packets exist only for an in-memory
model request; raw source bodies are not persisted in output artifacts or
telemetry.

## Limits

Python syntax and complexity use the standard-library AST. Other supported
languages use conservative declaration and import patterns. State, trust,
tests, and deployment results are candidates, not runtime proof. Git analysis
is consumed only from an optional pre-staged `architecture_git_history.json` or
`git_history.json`; the worker does not invoke Git. Dynamic loading, executed
tests, compiler semantics, performance behavior, and security posture require
separate evidence. A missing signal is `unknown`, never proof that risk is
absent.

## Validation

```bash
.venv/bin/python -m pytest tests/test_manifest_contracts.py -q
.venv/bin/python -m pytest tests -q
git diff --check
```
