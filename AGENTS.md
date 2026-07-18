# AGENTS.md

Guidance for future coding agents working in this repository.

These instructions apply only to `otterdesk-blueprints`.

## Start Here

Read repository `SPEC.md`, `README.md`, and `DAG_FLOW_PATTERNS.md`. For the
target blueprint, read its complete `README.md`, `SPEC.md`, `manifest.json`,
configuration, payload entrypoints, and tests before editing. Check `git status`
and preserve unrelated work.

Root `index.json` is the catalog inventory and identity source. Do not infer the
current catalog from a README table or from folders alone. Each blueprint is a
self-contained product contract; do not transfer domain rules between
blueprints without an explicit shared dependency.

## Issue Fixing Policy

- Unless the user explicitly asks for a temporary workaround, fix the root cause in the intended layer or contract.
- Avoid adding fallback paths, compatibility shims, feature flags, or temp solutions that mask a broken primary path.
- If fallback behavior is already product-specified, keep it narrow, documented, and tested; do not use it to avoid fixing the primary path.

## Architecture Ownership

Keep product composition, workflow orchestration, executable workers, reusable capabilities, and platform contracts in separate layers. Do not solve an ownership problem by creating a large shared blueprint module.

### Blueprint

A blueprint is the product- and domain-specific composition layer. It may own:

- the source manifest, configuration defaults, prompts, knowledge, examples, and output contracts;
- logical workflow steps and their step-to-step dependencies;
- domain policy, deterministic domain formulas, report structure, and customer-facing assumptions;
- thin executable bindings from registry agent IDs to their worker implementations.

A blueprint must not own generic message delivery, Redis routing, ACK/retry/dead-letter behavior, generic source/sink/join controls, manifest compilation, or broadly reusable document/tool helpers. Extract those to the appropriate shared repository.

Keep blueprint-specific behavior in the uniform `payloads/domain/` package, split by responsibility. Do not create `payloads/agents/domain.py`, a generic operation router, or another monolithic compatibility facade. Agent modules must import only the specific domain modules they use.

### Payload domain package contract

Every blueprint payload uses exactly one domain package at `payloads/domain/`.
The package name is intentionally generic so the bundle has one stable layout;
the blueprint boundary comes from the staged payload root, not from a
blueprint-specific Python package name. New domain behavior belongs in a
small, responsibility-named module such as `intake.py`, `evidence.py`,
`research.py`, `reporting.py`, `runtime_services.py`, or a method-specific
submodule. Do not add `payloads/<blueprint>_domain/` packages or reintroduce
blueprint-specific aliases for the `domain` package.
When an existing implementation is still consolidated, a focused module may
expose its owned functions without copying them; keep one implementation
source and put all new behavior in the focused module that owns it.

### Workflow steps

A step is a logical phase and node in the workflow DAG, not a worker. Step IDs should be action phrases; agent IDs should name specialist roles. Keep the namespaces conceptually distinct.

Modules under `payloads/steps/` may define only:

- the step input contract and upstream/run-input mappings;
- the step output contract and mappings;
- the internal collaboration graph of one or more agents;
- optional boundary-only input/output hooks.

Use `StepSpec` flow primitives for internal collaboration. Use manifest `needs` only for logical step-to-step dependencies. Never encode internal agent communication as workflow-step relationships, and never put domain processing into a step module.

The compiler expands a logical step into `step_start -> internal agent graph -> step_end`. Generated core source/sink/join/control agents own boundary collection, routing, deterministic joins, and logical completion. Only the generated step sink may complete the logical step and publish its declared output.

### Agents

An agent is an executable specialist worker with one bounded responsibility. An agent may be reused by multiple steps, and one step may require several agents.

Agent requirements:

- expose a directly resolvable handler and keep the registry mapping discoverable;
- prefer a same-named module for specialist registry IDs, even when several workers share an executor factory;
- receive input through the route-neutral SDK message API and return bounded output plus artifact references;
- durably write large, sensitive, or authoritative results before returning;
- use the invocation idempotency key and deterministic artifact paths so duplicate delivery is safe;
- never name message senders, recipients, streams, or routes;
- never implement fan-out, fan-in, workflow dependency traversal, retry policy, or logical step/run completion.

Redis Streams are the live agent-message plane. Filesystem/workflow-state artifacts are the durable data plane. Messages should contain bounded coordination data and artifact references, not confidential documents, research ledgers, or full reports.

When multiple blueprints need the same agent lifecycle composition, entity queue, tool loop, review worker, or artifact-finalization worker, implement it in `mn-agents` and inject blueprint behavior. Do not copy the generic agent implementation into a blueprint.

### Skills

A skill is a reusable capability or tool behavior, not a workflow node and not an autonomous crew member. Skills may own domain-neutral operations such as document reading, hashing, redaction, packet grouping, evidence mechanics, browser/tool adapters, scoring primitives, or report utilities.

Skills must not own workflow routes, step dependencies, logical completion, Redis delivery policy, blueprint runtime lifecycle, or customer-specific product decisions. Keep them configurable and independent of a particular blueprint's agent IDs and step IDs.

Leave behavior in the blueprint when it expresses product-specific policy—for example VC diligence assumptions, VC valuation method policy, research missions, evidence thresholds, and report semantics. Move the underlying reusable mechanics to a skill when they are useful outside that blueprint.

### SDK

The SDK owns domain-neutral public contracts and deterministic compilation/runtime helpers, including:

- step and agent contexts;
- `receive_input` / `send_output` and artifact-reference serialization;
- `StepSpec`, flow primitives, validation, and manifest compilation;
- generic runtime configuration, workflow-state access, lifecycle hooks, and handler resolution;
- route-neutral envelope parsing and other cross-blueprint protocol behavior.

The SDK must not contain blueprint IDs, agent rosters, prompts, VC terminology, customer policy, valuation formulas, or report composition. If an API requires knowledge of a particular blueprint to work, it is in the wrong layer.

### Core runtime

MirrorNeuron core owns execution topology and delivery semantics: generated source/sink/join controls, Redis enqueue/claim/lease/ACK/retry/deduplication/dead-letter behavior, physical routing, and workflow ledger state. Blueprints and agents consume these contracts but do not reimplement them.

## Blueprint Runtime Boundary

`payloads/runtime/` is limited to dependency/bootstrap preparation, validated configuration access, context creation/persistence, shared-service preparation, observability/lifecycle hooks, finalization, and failure handling.

Do not place document processing, evidence modeling, research policy, valuation formulas, auditing, review prompts, rendering, or artifact composition in `runtime.py`. Runtime code must not import executable agent behavior. Add architecture tests that enforce this boundary; for large blueprints, keep `runtime.py` comfortably below 500 lines.

## Single Sources of Truth

Do not repeat descriptive manifest information in payload Python or `config/default.json`.

- `manifest.json` owns blueprint identity, workflow topology, contracts, dependency declarations, agent registry entries, handler bindings, roles, and immutable handler parameters.
- `config/default.json` owns operator-tunable runtime values and may override manifest-owned defaults; it must not copy whole manifest descriptor sections.
- Payload Python derives agent rosters, workflow step IDs, scorer/method bindings, prompt-file conventions, accepted run-input keys, and similar descriptors from the staged source manifest or resolved runtime config.
- `skill_dependencies` and `agent_dependencies` are installed by the platform from the manifest. Never add a payload dependency bootstrap module or duplicate package lists in Python.
- Use `config.manifest_defaults` when a manifest descriptor must also be available through resolved runtime configuration. A dotted string preserves the same path; a `{ "from": ..., "to": ... }` mapping projects it to a runtime-config path. Runtime and compiler code must use the SDK resolver so manifest values merge before config-file and invocation overlays.
- Keep executable policy and algorithms in code: formulas, evidence confidence rules, report semantics, and other blueprint-specific behavior are not descriptive manifest data.

## Bundle Paths

- Use the SDK-owned `@/` prefix when configuration refers to a path inside the blueprint source bundle. For example, `@/examples/sample_inputs` addresses the bundle-root examples folder and `@/payloads/knowledge` addresses the payload knowledge folder.
- Do not put a blueprint directory name into a relative path (for example, `vc_assistant/examples/...`) and do not add `default_config_value`/`source_path` aliases to compensate for an ambiguous path.
- Launch-time local-input staging resolves source-root references and rewrites linked config fields to their staged runtime paths. Runtime payload references resolve against the worker's staged payload root. Blueprint agents must consume the resolved config and must not implement their own `@/` parsing.

When a value changes for structural reasons, it usually belongs in the manifest. When an operator should tune it per run, it belongs in config. When it computes or enforces domain behavior, it belongs in the owning agent, skill, or blueprint domain module.

## Placement Test

Before adding code, ask:

1. Is it a customer/domain decision or product composition? Put it in the blueprint domain package.
2. Is it a logical phase contract or internal agent graph? Put it in `payloads/steps/`.
3. Is it an independently invoked specialist responsibility? Put its entrypoint in `payloads/agents/`.
4. Is it a reusable capability with no routing or lifecycle ownership? Put it in `mn-skills`.
5. Is it reusable agent lifecycle/worker composition? Put it in `mn-agents`.
6. Is it a cross-blueprint Python contract, compiler primitive, or runtime helper? Put it in `mn-python-sdk`.
7. Is it physical workflow execution or Redis delivery semantics? Put it in MirrorNeuron core.

If code fits more than one layer, separate the reusable mechanism from the blueprint-specific policy and inject the latter through a narrow interface.

## Validation Expectations

For architecture-affecting blueprint changes, test the affected layers in their owning repositories:

- blueprint step definitions, agent handlers, artifact equivalence, and architecture guards;
- SDK message/envelope serialization and manifest compiler behavior;
- reusable agent idempotency and durable-output ordering;
- skill behavior independently from the blueprint;
- core source/sink/join, workflow-ledger, and Redis delivery behavior when those contracts change.

Architecture tests should reject agent/step naming confusion, missing registry handlers, `agents/domain.py`, domain imports from runtime, routing fields in agent payloads, nonexistent artifact references, and logical completion emitted by domain agents.

## Verification Workflow

Install only the test dependencies and declared sibling packages required by
the target suite, then run:

```bash
python -m pytest tests/test_manifest_contracts.py -q
python -m pytest tests/test_<blueprint>.py -q
python -m pytest tests -q
git diff --check
```

The suite intentionally consumes sibling `mn-python-sdk`, `mn-agents`, and
`mn-skills` contracts. Do not copy or vendor those implementations here to make
a test pass. Live models, network research, cameras, voice services, email, and
other external side effects are opt-in and are not part of the default catalog
gate.
