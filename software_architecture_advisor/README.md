# Architecture Advisor

Architecture Advisor 3.0 reviews large repositories piece by piece with the
OpenCode skill inside OpenShell. It evaluates the supplied report library's
**150 aspects in 23 sections**, including an independent counterevidence review
for each aspect, and produces explicit coverage even when evidence is missing.

## Run

```bash
mn blueprint run ./software_architecture_advisor \
  --set inputs.payload.repository_url= \
  --set inputs.payload.input_folder=/absolute/path/to/repository
```

The default URL is `https://github.com/homerquan/Archmind`. Supply exactly one
source: a public HTTPS GitHub repository root or a local folder. The platform
stages local input; reviewed source is never imported or executed. Public Git
clones retain the existing bounded, credential-free acquisition policy.

Default model: **Muse Spark 1.3 FreeOpenCode Zen**
(`opencode/muse-spark-1.3-contributor-free`). Override with
`--set opencode.model=provider/model`; update the OpenShell provider/network
policy for a different provider. There is no automatic paid-model fallback.
Bounded source excerpts are sent to the selected provider. OpenCode public
sharing, edits, shell execution, delegation and web tools are disabled for review.

The platform prepares `mirror-neuron/software-architecture-advisor:local` from
`payloads/docker_worker/Dockerfile` using the standard Python 3.11 base with
the declared SDK, agent and skill packages. This single-stage Dockerfile has no
`USER` instruction, as required by the SDK skill-preparation hook contract. The OpenShell reviewer builds its own declared context at
`payloads/openshell_worker/Dockerfile` before sandbox creation. It includes
OpenCode 1.18.33, Python and `iproute2` for network isolation; the platform
installs declared packages into that image. An existing Docker-worker image
tag is not used for sandbox provisioning. The execution host needs Docker and a working OpenShell gateway.
Do not launch the packet worker natively; live calls verify the OpenShell runtime.
The sandbox policy permits OpenCode Zen and the configured Local Spark model endpoints. Model changes
may require an explicit policy and credential-provider change.

## Choose the model

The blueprint setup form includes **OpenCode review model** with two choices:

| Choice | `opencode.model` |
| --- | --- |
| Muse Spark 1.3 FreeOpenCode Zen (default) | `opencode/muse-spark-1.3-contributor-free` |
| Muse Glimmer 30BLocal Spark | `spark/muse-glimmer-30b` |

Change `opencode.model` in `config/default.json`, or override it per run:

```bash
mn blueprint run ./software_architecture_advisor \
  --set opencode.model=spark/muse-glimmer-30b \
  --set inputs.payload.repository_url= \
  --set inputs.payload.input_folder=/absolute/path/to/repository
```

Both display labels are also accepted as configuration values. Local Spark uses
`opencode.spark_base_url` (default `http://10.0.4.32:8000/v1`), matching this
workstation's OpenCode provider configuration. The worker writes only the selected
provider configuration inside the sandbox. Changing that endpoint also requires
updating `payloads/openshell_worker/policy.yaml`; the sandbox must reach the local
server. Model selection is frozen for the run; change it before starting a new run.

## Workflow

1. Capture immutable UTF-8 source text, file hashes and available Git revision.
2. Build the existing source-linked dependency baseline and bounded DSM.
3. Initialize a durable task catalog and execute Core-managed child rounds:
   source packets → 150 aspect analyses → 150 challenges → evidence-driven
   follow-ups → 23 section syntheses → executive synthesis.
4. Revalidate evidence and publish the final report and linked registers.

Each worker handles one task and returns a bounded artifact reference. Core owns
execution, dependencies and round barriers; workers do not dispatch other
workers. Serial dependencies within a round protect shared output synchronization.
The planner admits new follow-ups only for known packet IDs with evidence from
completed parent tasks; duplicates, unsupported references and depth beyond two
are rejected. At most 64 dynamic follow-ups are admitted.

The default ceiling is 1,024 tasks/calls, 20 rounds, 64 tasks per round and 24
hours. A small repository still plans **324 catalog tasks plus source packets**.
Each source packet is at most 24,000 UTF-8 bytes; each model prompt is at most
60,000 bytes. Each call has a 600-second deadline and 1 MiB output ceiling.
Large source inventories reserve capacity for report synthesis and record omitted
packets explicitly. Lower call/time budgets produce partial reports, not positive
health assessments. Full reviews can take hours; the defaults are ceilings.

Configuration is in `catalog_review` and `opencode`. Existing capture limits are
5,000 files, 500 KB/file and 20 MB aggregate; tune `ingest` for larger repositories.
Unsupported extensions, symlinks, excluded directories and oversized/non-UTF-8
files retain capture limitations. Polyglot text reviews do not require Python
modules; automatic structural graph extraction remains primarily Python, with
optional evidence-backed graph exports for other languages.

`offline=true` is an explicit orchestration/coverage check. It makes no OpenCode
calls and marks all tasks `not_analyzed`; it never substitutes synthetic findings
for failed live analysis. Model failures or malformed citations become blocked
task records. Attempt reservations prevent automatic re-execution after an
interruption; use a new run for an explicitly chosen retry.

## Results

Authoritative artifacts remain in the SDK-provided shared run directory under
`$MN_HOME/shared/submissions/<submission-id>/outputs/runs/<run-id>/`. The SDK
handles the configured convenience copy to `~/Downloads/architecture-advisor`.

- `report.md`, `report.json`, `review_index.json`: overview and navigation.
- `sections/`: 23 reports with per-aspect requirements, conclusions and challenges.
- `coverage.json`: all 150 applicability/coverage decisions and source packet scope.
- `evidence.json`, `claims.json`, `findings.json`: immutable locators and traceability.
- `recommendations.json`, `assumptions.json`, `verification_tasks.json`:
  proposed decisions and the evidence still needed.
- `roadmap.json`, `work_packages.json`, `work_packages/`: proposed migration
  sequences and self-contained, evidence-linked coding-agent briefs.
- `catalog/`: immutable plans, requests, attempt budget, results, receipts and
  terminal reason. This audit data is confidential.
- `analysis/dependencies.json` and optional `analysis/dependency-dsm.csv`:
  deterministic structural evidence.

Empty recommendation/work-package registers mean no supported proposal was
produced. They do not mean the system is healthy. Runtime behavior, security,
capacity, organizational ownership, history and business costs remain unknown
unless supplied evidence supports a carefully scoped claim. Proposed work is
never authorization to change source, production data or deployments.

The complete original specification library is bundled at `payloads/report_specs`
with its manifest and hashes, so jobs do not depend on the author's host path.

## Validation status

The orchestration, evidence validation and report publication checks pass. The
2026-09-28 live OpenShell check reached OpenCode Zen but the default free model
returned HTTP 403. That run produced an explicitly blocked/partial report; it
was not a completed architecture assessment. No alternative model was selected.
See [validation details](VALIDATION.md) for tested scope and remaining gates.

The review worker uses `mn.artifact_handoff/v1`. Planning freezes each prompt and
reserves its task's model budget on the owner before dispatch. OpenShell receives
only immutable admission inputs; it never receives the writable SQLite ledger.
After Core commits a task's result, the owner verifies it against frozen evidence
and writes the domain receipt. Missing or ambiguous results retain their budget
reservation and block automatic task replay. Serial task ordering is preserved.
