# Drug Discovery Research Assistant Batch SPEC

## Purpose

Run one human-review-only computational discovery cycle and return five distinct evaluated molecules. It uses the local BioTarget pipeline and `homerquan/DrugClip` text↔molecular-graph model to produce and prioritize candidate hypotheses, runs folding and simulation adapters, and retains cycle-level evidence then complete review and reporting automatically.

## Scientific pipeline

1. BioTarget Stage C builds a molecular candidate pool and uses DrugClip graph-text alignment to select candidate hypotheses for the configured therapeutic text.
2. Folding fans out by target across the `science-folding` pool.
3. DrugCLIP fans out target–candidate screening across the `science-drugclip` pool.
4. Simulations fan out over the best DrugCLIP-ranked candidates across the `science-simulation` pool.
5. The native control worker gathers five distinct evaluated molecules and writes one cycle report. Review and ranking then produce the final artifact, and the batch terminates.

The blueprint-owned, job-scoped web UI presents these cycle phases beneath the logical five-step workflow. It is declared as an auxiliary entrypoint, so manifest expansion launches it alongside—not instead of—the compiler-generated `target_discovery__start` workflow root. Its labels come from the source manifest, and its status comes from workflow events plus `workflow_state/drug_discovery_state.json`, `service_state.json`, `cycle_progress.json`, `leading_candidate.json`, and `final_artifact.json`. Once a cycle is ranked, the Docker worker uses RDKit to write a local `leading_candidate.svg` 2D depiction. The UI exposes that one leading candidate's identifier, SMILES string, and bounded computational scores; the full candidate pool, private structure paths, and input text are not copied into its state response. The shared web-UI skill only registers the job-scoped external-URL handle; the blueprint owns its scientific rendering and read-only HTTP service.

DrugClip is the problem-specific scientific checkpoint `homerquan/DrugClip`, loaded by the BioTarget adapter as `best.ckpt`. `mirrorneuron-use-generic-model-skill` validates the explicit Hugging Face reference before the model-specific adapter downloads the matching checkpoint and instantiates native `DrugCLIP`. DrugClip is never added to the shared LLM model list, and Docker Model Runner is intentionally not used for this checkpoint because the repository is not a DMR-compatible generative model. Its 3D graph and text encoders provide the BioTarget Stage C selection and Stage D toxicity-alignment path; live runs fail rather than substitute a synthetic model or score.

The specialist actors' explanatory LLM calls use the platform's logical `default` Docker Model Runner route with automatic endpoint resolution. The manifest does not declare a concrete shared LLM or `runtime_model`, so platform and operator model selection stays authoritative. This shared LLM route is separate from DrugClip's native checkpoint execution.

## NVIDIA CUDA requirement

The manifest hard-requires at least one NVIDIA CUDA GPU with at least 48 GB (49,152 MB) of memory. MirrorNeuron resource validation owns the hardware check and rejects Apple-Silicon, CPU-only, and undersized nodes before scheduling a workflow. Every specialist node uses one shared `MirrorNeuron.Runner.DockerWorker` configured with `gpus: all`; DockerWorker placement therefore also requires a qualifying NVIDIA node. Its CUDA/cuDNN image installs the SDK and agent dependencies, the native DrugClip stack, and GNINA `v1.3.2` for the selected GPU architecture. PyTorch is constrained to `>=2.12,<2.13`: 2.12 supports CUDA 13 with a C++17 extension ABI, matching GNINA v1.3.2's fixed C++17 build contract. The native DrugClip adapter repeats the CUDA requirement at model load time by rejecting a PyTorch runtime without CUDA; it never falls back to CPU execution.

## Native cross-box contract

Target discovery, structure generation, candidate generation, binding review, and reporting run in the shared NVIDIA `DockerWorker`. The worker owns the discovery worker and all real DrugClip/GNINA calls with the full `payloads/requirements.txt` stack plus the manifest-declared SDK and agent dependencies. Live cluster mode requires a native dispatcher command. The controller sends it a JSON job containing adapter name, target pool, expanded command, request path, output path, and request payload. BioTarget is bundled in `payloads/biotarget/`; the staged payload is preferred over any external source path. The dispatcher returns a JSON `result` or writes the output path. Missing dispatcher, bundled BioTarget package, checkpoint, GNINA binary, or adapter configuration is a live-run error.

## Service lifecycle

The discovery stage always executes one cycle, then returns for review and final reporting. A legacy unlimited-cycle override does not change this bound. The batch fails explicitly if generation or screening cannot supply five distinct valid molecules. Each cycle updates `service_state.json` and atomically advances `cycle_progress.json` through candidate generation, folding, DrugCLIP screening, simulation, and report publication. Detailed artifacts are written under `cycles/cycle-<id>/`, while the configured user-facing output folder is updated with `service_status.json`, `cycle_progress.json`, `candidates.json`, `latest_cycle_report.json`, `leading_candidate.json`, and `leading_candidate.svg` so a long-running job has observable output before it stops. Fake smoke tests use an explicitly labeled synthetic SVG placeholder when RDKit is unavailable; live runs never substitute that placeholder.

## Persistent job data

Durable knowledge, Milvus Lite data, and service state belong to the stable job,
not the blueprint ID or execution. Two jobs cannot observe each other's data.
Run cancellation and retention do not remove those resources.

The top-level Job response service remains readable when the discovery worker is
not running. It exposes bounded non-secret profile, schedule, lifecycle, and
latest-cycle context and cannot launch computation or advance a candidate.

## Safety and non-goals

All results are computational hypotheses. The blueprint does not synthesize compounds, run assays, make clinical claims, submit regulatory material, or send candidates to external systems. Fake adapters are limited to explicit mock/smoke-test configuration and are labeled synthetic in every artifact. BioTarget Stage D invokes the native GNINA executable in the selected NVIDIA DockerWorker; no nested Docker socket or CPU-emulation path is part of the live contract.

Output folder `{job_id}` is resolved by the submission SDK to the stable job ID, for example `~/Downloads/job_ddra-12345678`. The SDK copies remote outputs back to this directory on the submitting host. `candidates.json` contains five unique molecules; `final_artifact.json` contains their ranked evaluations. The existing live run retains its submitted configuration; these settings apply to new runs.
