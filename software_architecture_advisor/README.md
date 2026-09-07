# Architecture Advisor

`software_architecture_advisor` converts the Spark software architecture investigation project into a Docker-worker blueprint. It freezes repository sources, builds architecture graph views on demand, replans a bounded child workflow between evidence rounds, and publishes independently reviewed, cited findings with an implementation roadmap.

Provide exactly one input:

- `repository_url`: public HTTPS GitHub repository root, such as `https://github.com/pallets/itsdangerous` (optional `.git`). Credentials, non-GitHub hosts, branches in URLs, redirects, SSH URLs, query strings and fragments are rejected.
- `input_folder`: local source directory. The platform stages it for the worker. Clone private repositories yourself and supply the local folder.

Optional `goal` focuses the investigation. Optional `graph_export` supplies a version-1 or version-2 graph with exact source provenance. Python receives structural AST analysis; other supported source languages are retrievable text and require an export declaring modules for structural investigation. A repository without structural modules reports an explicit failure.

## Prepare and run

Use the companion workspace with the newly created shared graph skill until its next GAR skill release is published:

```bash
export MN_WORKSPACE_ROOT=/Users/homer/Projects/mirror-neuron-set
export MN_SKILLS_ROOT="$MN_WORKSPACE_ROOT/mn-skills"
cd /Users/homer/Projects/otterdesk-blueprints/software_architecture_advisor
python3 -m pip install -e "$MN_SKILLS_ROOT/graph_analysis_skill"
python3 prepare.py --target aarch64-unknown-linux-gnu
MN_USE_LOCAL_SKILLS=1 mn blueprint run ./ \
  --set inputs.payload.repository_url=https://github.com/pallets/itsdangerous
```

For a folder:

```bash
MN_USE_LOCAL_SKILLS=1 mn blueprint run ./ \
  --set 'inputs.payload.input_folder=/absolute/path/to/repository'
```

Select `x86_64-unknown-linux-gnu` when the Docker worker host is x86-64. Preparation downloads the SHA-256-pinned `mn-graph-engine` GAR binary release 0.0.1 through `graph_analysis_skill`, retaining its license. It also builds the pinned Python evidence-provider wheel using host Git credentials. No credentials or graph-engine source are put in the Docker build context. Generated binaries and wheels are ignored by Git. Python dependencies install inside the worker image; the platform installs manifest-declared skills and agents.

The GAR skill dependency `mirrorneuron-graph-analysis-skill==1.3.23` is the forthcoming release containing this capability; use the local-skill command above until it is published. The graph-engine binary itself is already published. Authenticated `gcloud` access to the supplied GAR repository and Git access to the pinned Python provider package are required during preparation.

Live mode uses the platform's configured chat and embedding model bindings, normally Docker Model Runner. `config/default.json` controls the investigation and ingestion budgets; the LLM extension controls platform model selection. `--set offline=true` explicitly selects deterministic hypothesis checks with hash embeddings and zero model requests. Offline conclusions remain inconclusive review candidates. Provider failures never switch a live run to offline output.

## Results

Outputs include `investigation-plan.json`, immutable per-round plans and results under `investigation/`, `report.md`, `suggestive_prompts.md`, `report.json`, `knowledge.json`, `model-trace.json`, `events.log`, `snapshot.json`, `investigation.json`, and `review_index.json`. The `evidence/` directory retains immutable source text, graph generations, exact source spans, hashes, graph inputs, and acquisition checkouts. Runtime messages contain bounded counts/status and artifact references, not source text or full reports.

The three logical phases are `capture_repository`, `investigate_architecture`, and `publish_architecture_review`. The middle step contains a Core-managed child workflow. A planner commits a finite graph; graph-query, semantic-search, assessment and summary specialists execute it without replanning. The next planner invocation receives the completed evidence round. Their specialist workers use the shared stateful agent lifecycle. Only platform-generated step sinks complete logical steps. Docker runs Python 3.11 on Debian Bookworm with the published CPU RGX binary; it never builds Rust.

## Interpretation limits

Twenty architecture families plus an embedding index are built only when requested. Expensive control-flow, data-flow, security, and semantic views are module scoped. Python import edges are static dependencies, SQL literals do not prove physical database identity, test calls are not executed coverage, and commit co-change is not incident causality. Runtime workflows and incidents need supplied evidence. Missing evidence is explicit; top-k absence is never proof of absence.

Repository code, hooks, tests, package installers, submodules and LFS downloads are not executed. GitHub acquisition is shallow, bounded by time and commit depth, and retained separately per snapshot. Captured source text and model traces may contain confidential material. General knowledge cards guide review but cannot serve as project citations. Inconclusive advice generates characterization or verification tasks before a structural change.

## Validation

```bash
python -m pytest tests/test_software_architecture_advisor.py -q
python -m pytest tests/software_architecture_advisor -q
```

Run these from the catalog root. Domain tests are offline. Set `ADVISOR_RGX_BINARY` to the published Linux binary when running real graph integration tests in a Linux Docker worker. See `SPEC.md` for the product and evidence contract.

## Dynamic investigation (v2)

Version 2 requires the SDK compiler and Core child-workflow support from the companion workspace. Deploy those together before submitting this blueprint; no package release is published by these changes. Older runtimes cannot execute this declaration.

Defaults are three rounds, three hypotheses per round, six distinct hypotheses, sixty graph/search operations, thirty chat-model calls (including repairs and lazy semantic graph inference), and a twenty-minute investigation budget. Six calls are reserved for independent final review. Embedding ingestion retains its separately bounded source limits. Candidate-module context is a goal-ranked page of up to 48 modules plus previous finding modules; the planner sees the omitted count.

Planner decisions and committed parameters are immutable artifacts. Core retains the child phase, revisions, dependency graph and outcomes in its ledger. Completed workers and recorded model responses are reused. An interrupted request with no durable response fails explicitly instead of guessing its result. Corrupt evidence and live-provider failures fail the run. Budget exhaustion publishes an explicitly incomplete report containing verified results, with unreviewed changes excluded from the roadmap.

The report prioritizes independently reviewed findings by evidence and goal relevance. Every roadmap item includes an action, acceptance check and rollback. Inconclusive advice proposes verification; its rollback preserves all pre-existing application changes.

The opt-in Linux worker smoke uses actual SDK handlers and RGX:

```bash
PYTHONPATH=/blueprints/software_architecture_advisor/payloads python \
  /blueprints/tests/software_architecture_advisor/linux_dynamic_smoke.py --output /output
```

Add `--live` to use the configured model gateway on the synthetic sample repository. The smoke uses hash retrieval to isolate chat planning/review from embedding-provider setup; normal live runs retain the configured neural embedding provider. Core's `tests/unit/child_workflow_test.exs` tests production scheduling, round barriers and parent completion separately.
