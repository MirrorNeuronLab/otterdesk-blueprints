# OtterDesk Blueprint Catalog Specification

## Purpose

`otterdesk-blueprints` is the self-contained product blueprint catalog consumed
by OtterDesk and MirrorNeuron tooling. Each catalog entry combines a source
manifest, launch configuration, domain payload, user documentation, safety
terms, and deterministic tests into an installable co-worker/workflow bundle.

This specification applies only to this repository. Reusable agents, skills,
SDK compilation, and Core delivery are dependencies, not code owned here.

VC Assistant uses foundational `mn_sdk.llm` access through blueprint support
and does not declare `mirrorneuron-litellm-communicate-skill`. Its RAG and OCR
skills own their complete model specifications and pass them to the SDK's lazy
runtime model wrapper. VC Assistant declares only the skills and product-level
behavior; first-use runtime selection chooses and prepares the concrete DMR
model. This migration does not change other blueprints.

## Catalog Contract

Root `index.json` is the authoritative list of published blueprint identities,
versions, paths, and catalog metadata. `category.json` defines shared catalog
categorization. A folder not present in the index is not a published catalog
entry; an index entry without a valid folder is invalid.

Each published blueprint provides, as applicable:

```text
<blueprint>/
  README.md
  SPEC.md
  TERM.md
  manifest.json
  config/default.json
  config/overwrite.json
  payloads/
```

`manifest.json` uses the readable `mn.workflow.source/v2` contract and owns
identity, topology, contracts, registry bindings, immutable handler parameters,
requirements, and declared dependencies. `config/default.json` owns tunable
defaults; committed overwrite files contain no user secrets.

## Blueprint Ownership

A blueprint owns product/domain composition:

- the mission, user inputs, domain assumptions, safety limits, and outputs;
- logical step contracts and direct `needs` dependencies;
- specialist registry bindings and internal collaboration definitions;
- domain prompts, formulas, evidence/review policy, and report semantics; and
- deterministic artifact naming and customer-facing documentation.

It does not own generic message delivery, ACK/retry/dead-letter behavior,
source/sink/join controls, manifest compilation, reusable tool mechanics, or
shared agent lifecycle composition.

## Runtime Layout

- `payloads/domain/` is the single domain package and is split into focused
  responsibility-named modules.
- `payloads/steps/` defines logical step I/O mappings and internal `StepSpec`
  collaboration only; it contains no domain processing.
- `payloads/agents/` exposes bounded specialist handlers with discoverable
  registry mappings.
- `payloads/runtime/` is limited to config/context/service preparation,
  lifecycle/observability, persistence, finalization, and failure handling.
- Docker, host, OpenShell, or Beam payload assets stay in explicit sibling
  payload directories.

Core expands logical steps to generated boundary controls. Domain agents never
complete logical steps, implement physical routes, or traverse workflow
dependencies.

## Data and Artifact Contract

Live coordination messages contain bounded data and artifact references. Large,
sensitive, or authoritative results are durably written before a handler
returns. Duplicate delivery is safe through invocation idempotency and
deterministic artifact paths.

Bundle-local config paths use SDK `@/` references and are resolved by the shared
staging/runtime contract. Blueprint code consumes resolved paths and does not
implement alternate path syntax.

Persistent cross-run state is explicit in `metadata.job_data.resources`.
Resources declare a logical name, validated relative job-data path,
`read_only`/`read_write` access, and optional bundle-local `@/` directory seed.
The stable `job_id`, not blueprint ID or `run_id`, is the storage isolation
key. Seeds apply only on initialization and explicit data reset. Knowledge,
Milvus Lite databases, and durable application state remain job-scoped; run
inputs, outputs, logs, and ordinary artifacts remain run-scoped.

Blueprints must not derive host storage paths, treat replication as a
transactional filesystem, or clear job data during run cleanup. Mutable
file-backed resources require Core owner-node placement and the declared access
mode. Two jobs using one blueprint must remain mutually isolated.

## Documentation and Safety

Each blueprint README explains setup, smallest safe run, inputs/outputs, and
inspection. Its SPEC states current outcomes, evaluation criteria, contracts,
limits, risks, and non-goals. TERM records domain/legal assumptions where used.
These documents, manifest, config, payload behavior, catalog metadata, and tests
must agree.

Blueprints never commit customer data or secrets. External network, camera,
voice, email, filesystem, model, GPU, and sandbox capabilities are explicit in
requirements and user documentation. Review-only outputs are not presented as
professional, legal, medical, financial, scientific, or security guarantees.

## Versioning

Changes to required inputs, topology, outputs/artifacts, default domain policy,
side effects, safety boundaries, dependencies, or evaluation semantics require
a blueprint version/compatibility review and synchronized catalog metadata.
Additive optional config is compatible only when omission preserves behavior.

## Acceptance

The default suite validates catalog/index consistency, source manifests,
registry handlers, package dependencies, runtime/step/domain boundaries,
artifacts, documentation, and blueprint-specific deterministic behavior:

```bash
python -m pytest tests -q
```

Live external capabilities remain explicit opt-in checks. Contract changes in a
sibling SDK/agent/skill/Core layer are tested in that owning repository as well
as through the affected catalog integration.
