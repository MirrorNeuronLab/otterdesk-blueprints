# Software Architecture Advisor

`Blueprint ID:` `software_architecture_advisor`  
`Category:` `Engineering`

Software Architecture Advisor is an air-gapped, read-only architecture review
for a single software repository. It inventories the staged source, builds a
syntax/symbol and dependency fact database, reconstructs state, trust, test,
and deployment boundaries, triangulates change-risk hypotheses, and produces
prioritized improvement prompts for an AI coding agent. Eight required,
specialist passes through the logical `medium` local-model route perform
investigation planning, reconstruction, cross-cutting analysis, finding
synthesis, adversarial review, prompt authoring, report synthesis, and final
audit.
It never modifies, executes, builds, tests, installs, or uploads the target
project.

## Requirements

This blueprint requires at least **48 GB of host memory** and the runtime's
`medium` local-model route. The platform selects a capable node, resolves that
logical route to its concrete installed model, and injects the node's reachable
model gateway and lazy model-control service into Docker workers. The blueprint
never hardcodes a model artifact, node, or direct model-runner endpoint and
never downloads a model itself.
Normal runs require real provider responses and fail if any pass falls back.
The model contract declares `structured_output` and `thinking` through the SDK's
`required_capabilities` runtime interface. The SDK rejects a cataloged mismatch
before inference; unknown capabilities are checked once against the prepared
loopback endpoint and cached in the user model catalog for later runs.

## Input

Provide a non-empty `input_folder` before starting the job. It must be the
local source snapshot to inspect:

- `input_folder`: a local folder containing the source snapshot to inspect.

`analysis_focus` can call out a concern such as modularity, reliability,
migration risk, or data ownership. The input source is treated as untrusted
data; embedded instructions in source comments or documentation never override
this blueprint's policy.

No source repository is bundled with the blueprint. Clone, export, or otherwise
prepare the source locally, then select its folder as `input_folder`.

## Quick start

For a local codebase, supply an absolute path:

```bash
mn blueprint run ./software_architecture_advisor \
  --set inputs.payload.input_folder=/work/acme-service \
  --set 'inputs.payload.analysis_focus=["module boundaries","testability"]'
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
  state/trust/test/deployment models, optional local Git-history evidence,
  architecture reconstruction, adversarial review, prioritized findings, and
  `llm_analysis.json` with the validated output and usage provenance for all
  eight model stages.
- `llm_trace.jsonl` — metadata-only provider/model/latency/token/retry/fallback
  records. It excludes prompts, source excerpts, credentials, and full model
  responses.
- `architecture-report/` — numbered reviewer views for repository structure,
  dependencies, hotspots, state, trust boundaries, tests, and migration order.
- `prompts/` — an indexed folder containing one standalone `.md` prompt per
  prioritized finding. Open `prompts/README.md`, choose a prompt, and paste it
  into Codex or another coding agent.

Prompts recommend changes but never perform them. They explicitly instruct a
coding agent to inspect the cited paths, preserve behavior, add or update tests,
and stop for human direction when the evidence is insufficient.

## Analysis process

1. Validate the supplied local source folder.
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
selected node's local model gateway. The blueprint requests the logical
32k-context `medium` profile. Before every model call it reserves that profile's
maximum completion tokens plus a safety margin, estimates the complete
serialized input, and compacts bounded source excerpts or repeated structured
evidence to fit the remaining input-token budget. Structured stages retain all
facts already cited by their findings and maps before filling remaining space
with optional facts. The analysis profile reserves up to 16,000 completion
tokens so the reasoning model can finish the required JSON instead of spending
its entire allowance before producing the answer. A request that still cannot
fit fails before model dispatch with an explicit budget diagnostic. Source
code, secrets, and reports are not sent to external services. Bounded source
packets exist only for an in-memory model request; raw source bodies are not
persisted in output artifacts or telemetry.

## Limits

Python syntax and complexity use the standard-library AST. Other supported
languages use conservative declaration and import patterns. State, trust,
tests, and deployment results are candidates, not runtime proof. Git analysis
is consumed only from an optional local `architecture_git_history.json` or
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

## Blueprint package format

This blueprint uses the canonical blueprint/v1 format in both folders and ZIPs.
`manifest.json` contains identity, semantic release version, and document references.
`workflow.json` owns logical topology and policies; `execution.json` owns workers,
resources, and services; `contracts.json` owns input/output and artifact contracts.
Platform descriptors live in `extensions/`, package requirements in
`dependencies.json` when present, and operator defaults in `config/default.json`.
The SDK reads these documents together and compiles the Core execution artifact.
A ZIP contains the same files as the folder. Local overrides and invocation
configuration are resolved by the SDK before launch.
