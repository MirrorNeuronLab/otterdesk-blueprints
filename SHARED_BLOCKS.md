# Shared block ownership

The table maps common work to the SDK that owns it. Blueprints supply domain
decisions through the v1 authoring API. The historical audit below also covers
packages that have since left the published catalog. See the current inventory
in [index.json](index.json) and the [authoring guide](how_to_create_blueprints.md).

| Mechanic | Shared owner | Blueprint responsibility |
| --- | --- | --- |
| Defaults, explicit run inputs, linked path aliases, and `@/` | `mn_sdk.blueprint.inputs.declared_inputs` and staging | Declare input contracts and local inputs |
| Resolved input artifacts | `capture_declared_inputs` / `save_declared_inputs` | Normalize domain values before saving when needed |
| Optional input path selection | `configured_input_path` | Choose which domain input is needed |
| Runtime output and persistent Job directories | `BlockContext.output_directory` / `job_directory` | Choose domain-relative files and resources |
| Committed JSON and nested evidence verification | `BlockContext.read_evidence` / `read_checkpoint` | Validate phase, scientific/legal/financial scope, and domain invariants |
| Immutable artifact receipts and output delivery | `publish_artifact_bundle`, `publish_files`, and stock publication blocks | Select content, required artifacts, and optional presentation |
| File snapshots and restoration | Existing `capture_file` / `materialize_file` | Select authorized sources and domain size/format limits |
| Atomic JSON/text/bytes, config merging, object JSON reads, and standard timestamps | SDK/common file and blueprint-support helpers | Produce domain values and retain domain-specific publication ordering and link checks |
| Cancellation, deadlines, retries, effect reconciliation, and lifecycle | Existing common block execution/checkpoint/capability APIs | Check cancellation between domain work and retain approval policy |

`@/examples/sample_inputs` is a blueprint-root reference. Staging updates config
and workflow input seeds together. Ordinary staged relative paths use the worker
root, including an explicit `.`. Omitted/null ports use configured defaults.
SDK config overlays synchronize changed primary/linked fields before staging;
conflicting explicit aliases fail. Original operator configuration remains immutable; resolved input artifacts
contain the selected runtime paths. Full credential-bearing configuration is not
copied into input artifacts.

## Catalog audit

| Blueprint | Shared behavior used after the audit |
| --- | --- |
| Drug Discovery | Input capture, runtime destinations, evidence reads, receipt delivery, atomic files, config merge/read helpers |
| Financial Advisor | Input aliases/defaults, input saving, runtime destinations, evidence reads, common capability dispatch/replay, observed model outcomes and usage, receipt delivery, timestamp helper |
| Procurement Manager | Input defaults and paths, input saving, runtime destination, evidence reads, receipt delivery |
| Research Assistant | Input defaults with its existing empty-answer policy, input saving, runtime destination, evidence reads, receipt delivery |
| VC Assistant | Input capture, linked paths, runtime destination, existing portable file capture and scoped checkpoints; redundant slug wrapper removed |
| Software Architecture Advisor | Input capture and paths, runtime destination, nested evidence verification, atomic snapshots/history; domain snapshot and catalog authority checks retained |
| Code Verifier | Input capture and paths, Job directory, existing common atomic writes and publication primitives; software-rule policy retained |
| General Assistant | Input defaults/paths/saving, existing checkpoint and publication APIs; Harness2 quotas, private memory and sandbox policy retained |
| CT Reader | Shared input capture before the existing native computation block; medical-research input policy retained |
| Litigation Analyst | Input capture and paths, atomic identity-ledger storage, existing scoped checkpoints and file validation; citation checks, legal scope and archive-link layout retained |
| Mac Security Investigator | Shared Job directory and existing stock report publication; host epoch and temporal evidence policy retained |
| CCTV Operator | Native NVIDIA DockerCompose service plus one SDK-monitored streaming operator, durable caption accounts and final activity publication |
| Microduck Controller | Existing controlled-operation, event-processing and monitored-service blocks; shared atomic state publication; simulator and operator command policy retained |
| ROS AMR Controller | Already uses stock Compose lifecycle; only robot-specific result content remains in its finalizer |
| Web Lab Operator | Shared input capture/staging, structured assessment, managed model journals, scoped checkpoints, Membrane TextMemory/typed recall, Web UI binding/claims and verified publication; liquid-handling and experience-selection policy remain domain-owned |
| GTM Planner | Existing shared runtime configuration, workflow storage and monitored lifecycle; campaign planning/approval policy retained |
| GTM Executor | Existing shared runtime configuration and monitored lifecycle; recipient suppression, transactional send receipts and uncertain-send policy retained |

Stable domain identifiers deliberately retain their existing serialization and
hashing rules. Changing these while extracting a generic helper could invalidate
saved evidence, deduplication keys or caches. Domain-specific archive layouts,
review qualifications, reports, model selection, safety limits and external-effect
authorization also remain in their owning blueprints.

The shared-contract tests exercise default input resolution and immutable storage for
every indexed package and both GTM packages, and reject per-blueprint runtime-path helpers and direct
`inputs.json` commits. SDK tests cover aliases, overrides, malformed paths,
symlink boundaries, cancellation, nested tampering, publication replay and
delivery recovery. Existing blueprint tests continue to verify domain outcomes.

The authoring API requires `mirrorneuron-python-sdk>=1.4.1.dev46,<2`.
Common and blocks are separately versioned in each package's `dependencies.json`.
Use matching installed components and reprepare the Job to pick up changes.
Existing definitions retain their compiled component identities.
