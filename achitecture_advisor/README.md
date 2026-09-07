# Architecture Advisor

`achitecture_advisor` converts the Spark software architecture investigation project into a Docker-worker blueprint. It freezes repository sources, builds architecture graph views on demand, tests bounded hypotheses against support and counter-evidence, and publishes a cited review with suggested follow-up tasks.

Provide exactly one input:

- `repository_url`: public HTTPS GitHub repository root, such as `https://github.com/pallets/itsdangerous` (optional `.git`). Credentials, non-GitHub hosts, branches in URLs, redirects, SSH URLs, query strings and fragments are rejected.
- `input_folder`: local source directory. The platform stages it for the worker. Clone private repositories yourself and supply the local folder.

Optional `goal` focuses the investigation. Optional `graph_export` supplies a version-1 or version-2 graph with exact source provenance. Python receives structural AST analysis; other supported source languages are retrievable text and require an export declaring modules for structural investigation. A repository without structural modules reports an explicit failure.

## Prepare and run

Use the companion workspace with the newly created shared graph skill until its next GAR skill release is published:

```bash
export MN_WORKSPACE_ROOT=/Users/homer/Projects/mirror-neuron-set
export MN_SKILLS_ROOT="$MN_WORKSPACE_ROOT/mn-skills"
cd /Users/homer/Projects/otterdesk-blueprints/achitecture_advisor
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

Outputs include `report.md`, `suggestive_prompts.md`, `report.json`, `knowledge.json`, `model-trace.json`, `events.log`, `snapshot.json`, `investigation.json`, and `review_index.json`. The `evidence/` directory retains immutable source text, graph generations, exact source spans, hashes, graph inputs, and acquisition checkouts. Runtime messages contain bounded counts/status and artifact references, not source text or full reports.

The three logical phases are `capture_repository`, `investigate_architecture`, and `publish_architecture_review`. Their specialist workers use the shared stateful agent lifecycle. Only platform-generated step sinks complete logical steps. Docker runs Python 3.11 on Debian Bookworm with the published CPU RGX binary; it never builds Rust.

## Interpretation limits

Twenty architecture families plus an embedding index are built only when requested. Expensive control-flow, data-flow, security, and semantic views are module scoped. Python import edges are static dependencies, SQL literals do not prove physical database identity, test calls are not executed coverage, and commit co-change is not incident causality. Runtime workflows and incidents need supplied evidence. Missing evidence is explicit; top-k absence is never proof of absence.

Repository code, hooks, tests, package installers, submodules and LFS downloads are not executed. GitHub acquisition is shallow, bounded by time and commit depth, and retained separately per snapshot. Captured source text and model traces may contain confidential material. General knowledge cards guide review but cannot serve as project citations. Inconclusive advice generates characterization or verification tasks before a structural change.

## Validation

```bash
python -m pytest tests/test_achitecture_advisor.py -q
python -m pytest tests/achitecture_advisor -q
```

Run these from the catalog root. Domain tests are offline. Set `ADVISOR_RGX_BINARY` to the published Linux binary when running real graph integration tests in a Linux Docker worker. See `SPEC.md` for the product and evidence contract.
