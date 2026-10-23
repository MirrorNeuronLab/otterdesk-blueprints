# Drug Discovery Research Assistant Batch SPEC

## Purpose

Run one human-review-only computational discovery cycle and return five distinct evaluated molecules. It uses the local BioTarget pipeline and `homerquan/DrugClip` text↔molecular-graph model to produce and prioritize candidate hypotheses, runs folding and simulation adapters, and retains cycle-level evidence then complete review and reporting automatically.

## Scientific pipeline

1. BioTarget Stage C builds a molecular candidate pool and uses DrugClip graph-text alignment to select candidate hypotheses for the configured therapeutic text.
2. Folding fans out by target across the `science-folding` pool.
3. DrugCLIP fans out target–candidate screening across the `science-drugclip` pool.
4. Simulations fan out over the best DrugCLIP-ranked candidates across the `science-simulation` pool.
5. The native control worker gathers five distinct evaluated molecules and writes one cycle report. Review and ranking then produce the final artifact, and the batch terminates.

After ranking, the blueprint domain package renders an optional run-scoped `web/index.html` result page from workflow events plus `workflow_state/drug_discovery_state.json`, `service_state.json`, `cycle_progress.json`, `leading_candidate.json`, and `final_artifact.json`. It also draws up to five ranked candidate SMILES strings as local RDKit SVG files and writes a `static_html` `web_ui.json` handle for the runtime proxy. The page is not an agent, entrypoint, service, or health-checked dependency. Rendering occurs only after the authoritative report is durable and any rendering failure is contained, so web UI preparation or availability cannot prevent the scientific batch from starting or completing. The page exposes the leading candidate's bounded computational scores and up to five ranked candidate identifiers, SMILES strings, and local RDKit SVGs. Private structure paths and input text are not copied into it.

The same optional render pass writes a generic `otterdesk.conversation_media.v1` manifest under `web/`, with run identity, bounded candidate labels and SMILES captions, and PNG previews. OtterDesk reads it from a published output location to show a stable image gallery in the co-worker conversation. The manifest is written after its image files. Missing previews do not alter the scientific result.

The optional page uses `mirrorneuron-web-report-skill` for the system report shell, offline fonts, navigation, Actions menu, and CSP. Blueprint code owns only the scientific views and molecule layout. Each available PNG has a SHA-256 in the conversation-media manifest for verified remote preview loading. The reporting block returns the SDK `published_files` contract with required scientific outputs and optional page/media outputs, including cycle evidence and adapter request/result files. Core owns transport and host delivery owns the output-folder result event. A completed computation must not depend on a blueprint-authored delivery event or filesystem-copy workaround.

DrugClip is the problem-specific scientific checkpoint `homerquan/DrugClip`, loaded by the BioTarget adapter as `best.ckpt`. `mn-python-sdk-models` validates the explicit Hugging Face reference before the model-specific adapter downloads the matching checkpoint and instantiates native `DrugCLIP`. DrugClip is never added to the shared LLM model list, and Docker Model Runner is intentionally not used for this checkpoint because the repository is not a DMR-compatible generative model. Its 3D graph and text encoders provide the BioTarget Stage C selection and Stage D toxicity-alignment path; live runs fail rather than substitute a synthetic model or score.

The specialist actors' explanatory LLM calls use the platform's logical `default` Docker Model Runner route with automatic endpoint resolution. The manifest does not declare a concrete shared LLM or `runtime_model`, so platform and operator model selection stays authoritative. This shared LLM route is separate from DrugClip's native checkpoint execution.

## NVIDIA CUDA requirement

The manifest hard-requires at least one NVIDIA CUDA GPU with at least 48 GB (49,152 MB) of memory. MirrorNeuron resource validation owns the hardware check and rejects Apple-Silicon, CPU-only, and undersized nodes before scheduling a workflow. Every specialist node uses one shared `MirrorNeuron.Runner.DockerWorker` configured with `gpus: all`; DockerWorker placement therefore also requires a qualifying NVIDIA node. Its CUDA/cuDNN image installs the SDK and agent dependencies, the native DrugClip stack, and GNINA `v1.3.2` for the selected GPU architecture. PyTorch is constrained to `>=2.12,<2.13`: 2.12 supports CUDA 13 with a C++17 extension ABI, matching GNINA v1.3.2's fixed C++17 build contract. The native DrugClip adapter repeats the CUDA requirement at model load time by rejecting a PyTorch runtime without CUDA; it never falls back to CPU execution.
The worker launches the SDK step runtime through `/opt/mn-venv/bin/python3`, the interpreter where the image installs its Python dependencies.

## Native cross-box contract

The simulation adapter accepts one `screens` batch and returns the corresponding
`simulations` in input order. It loads DrugClip once per batch, shares the
read-only model, and retains `service.parallelism.simulation_workers` concurrent
candidate evaluations. GNINA subprocesses use separate temporary ligand,
cleaned-receptor, and scratch files, removed on success or failure. The
one-active-run-per-node rule does not serialize model calls inside that run.

Target discovery, structure generation, candidate generation, binding review, and reporting run in the shared NVIDIA `DockerWorker`. The worker owns the discovery worker and all real DrugClip/GNINA calls with the full `payloads/requirements.txt` stack plus the manifest-declared SDK and agent dependencies. Live cluster mode requires a native dispatcher command. The controller sends it a JSON job containing adapter name, target pool, expanded command, request path, output path, and request payload. BioTarget is bundled in `payloads/biotarget/`; the staged payload is preferred over any external source path. The dispatcher returns a JSON `result` or writes the output path. Missing dispatcher, bundled BioTarget package, checkpoint, GNINA binary, or adapter configuration is a live-run error.

## Service lifecycle

The discovery stage always executes one cycle, then returns for review and final reporting. A legacy unlimited-cycle override does not change this bound. The batch fails explicitly if generation or screening cannot supply five distinct valid molecules. Each cycle updates `service_state.json` and atomically advances `cycle_progress.json` through candidate generation, folding, DrugCLIP screening, simulation, and report publication. Detailed artifacts are written under `cycles/cycle-<id>/`, while the configured user-facing output folder is updated with `service_status.json`, `cycle_progress.json`, `candidates.json`, `latest_cycle_report.json`, `leading_candidate.json`, and `leading_candidate.svg` so a long-running job has observable output before it stops. Fake smoke tests use an explicitly labeled synthetic SVG placeholder when RDKit is unavailable; live runs never substitute that placeholder.

## Persistent job data

Durable knowledge, DuckDB data, and service state belong to the stable job,
not the blueprint ID or execution. Two jobs cannot observe each other's data.
Run cancellation and retention do not remove those resources.

The top-level Job response service remains readable when the discovery worker is
not running. It exposes bounded non-secret profile, schedule, lifecycle, and
latest-cycle context and cannot launch computation or advance a candidate.

## Safety and non-goals

All results are computational hypotheses. The blueprint does not synthesize compounds, run assays, make clinical claims, submit regulatory material, or send candidates to external systems. Fake adapters are limited to explicit mock/smoke-test configuration and are labeled synthetic in every artifact. BioTarget Stage D invokes the native GNINA executable in the selected NVIDIA DockerWorker; no nested Docker socket or CPU-emulation path is part of the live contract.

Version 1.0.5 sets the default output folder to `~/Downloads/drug-discovery-research-assistant`, matching the declared job name. The SDK copies remote outputs back to this directory on the submitting host. `candidates.json` contains five unique molecules; `final_artifact.json` contains their ranked evaluations. The existing live run retains its submitted configuration; these settings apply to new runs.

## Native block composition (4.0.0)

All five phases bind SDK domain-operation blocks directly to the scientific
functions in `domain/native_stages.py`, `domain/continuous_service.py` and
`domain/reporting.py`. Operations consume `BlockContext` and immutable predecessor
references. The target and structure phases call the bundled BioTarget scientific
APIs directly. The cycle phase invokes the molecular generation, screening and
simulation pipeline with the captured research inputs and selected targets.

The SDK owns worker execution, cancellation and liveness beacons. The previous
phase/context bindings, private beacon implementation and five command-line
phase wrappers are removed. SDK storage binds captured structures and completed
cycle artifacts to their hashes; SDK bundles publish required scientific JSON
before the optional result dashboard and conversation media. Domain code retains
scientific ranking, five distinct candidates, GPU placement and review policy.

A saved cycle start without matching completed evidence requires reconciliation;
retrying cannot silently launch the scientific cycle again. Matching completed
cycle evidence is reused. Cancellation is checked between molecular phases and
scientific jobs. Live scientific failures remain failures. Explicit mock runs
are labeled `fake_smoke_test` in the final report and do not invoke live science.

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

## Context engine contract

Version 1.2.0 enables Membrane source intelligence through `source_context.enabled`
and declares `mirrorneuron-python-sdk[context]`. Before target discovery, the
worker publishes the approved research inputs, complete Markdown conversions of
staged JSON/CSV/text/Markdown documents, and the configured procedure. Saved
stage results and final rankings update separate scientific output sources under
`context_sources/{inputs,outputs}/` in the SDK-provided Job output folder. The
runtime Job responder ingests these prepared sources and returns cited answers
through `ask_job`, including while the scientific worker is stopped. Raw input
files are never opened by Chat.

Sources identify their Run and distinguish provided inputs, configured procedure,
saved findings, missing results, and synthetic smoke tests. Scientific output
projections exclude credentials, configuration, adapter commands, subprocess
diagnostics, and private receptor paths. These are private local research
artifacts: do not place credentials in the approved input documents. Curated
scientific guidance remains separate RAG knowledge; unused TextMemory runtime
recall remains disabled. Missing or oversized source evidence is explicit and
never replaced with invented findings.

The matching Membrane v2 CPU service and SDK are required. Each input batch is
limited to 64 approved files and 24 MiB of complete text; one prepared source is
limited to 4 MiB. Set `source_context.enabled=false` to opt out of source
publication and engine preparation. Existing submitted runs retain their
original package/configuration; updating the catalog does not rewrite them.

## Target selection

The default run uses the explicitly provided BACE1 UniProt target `P56817`.
`inputs.payload.targets` is a list of `{protein_id, gene}` records; supplied
targets are preserved rather than replaced by a general disease search. Clear
that list to discover disease-associated proteins through Open Targets, using
`inputs.payload.disease` (for example, `Alzheimer disease`). The separate
`disease_or_target_profile` remains the complete therapeutic intent for DrugCLIP
screening. It is never sent as a disease search query. Invalid target identifiers
fail explicitly; no unrelated targets are substituted. Source documents identify
whether the targets were provided or discovered.

## Standard MCP supervision

This package requires `mn.mcp.supervision.v1`. The SDK implements the shared manual, capabilities, context, results, activity, lifecycle, and operation tools. `knowledge/user_manual.md` is bundled with the prepared Job. Domain tools and their native JSON input/output schemas are declared once in `extensions/mcp.json`; response agents derive their bindings from it. All tool results use `mn.mcp.tool_result.v1`. Mutations require a request ID, and asynchronous work is observed through `get_operation_status`. Upgrade the installed SDK/API/desktop together and update idle Job definitions before using this contract.
