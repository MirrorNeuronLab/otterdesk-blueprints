# Drug Discovery Research Assistant Service SPEC

## Purpose

Operate a continuously running, human-review-only computational discovery service. It uses the local BioTarget pipeline and `homerquan/DrugClip` text↔molecular-graph model to produce and prioritize candidate hypotheses, runs folding and simulation adapters, and retains cycle-level evidence until an operator manually stops the service.

## Scientific pipeline

1. BioTarget Stage C builds a molecular candidate pool and uses DrugClip graph-text alignment to select candidate hypotheses for the configured therapeutic text.
2. Folding fans out by target across the `science-folding` pool.
3. DrugCLIP fans out target–candidate screening across the `science-drugclip` pool.
4. Simulations fan out over the best DrugCLIP-ranked candidates across the `science-simulation` pool.
5. The native control worker fans results in, writes a cycle report, and starts the next cycle.

DrugClip is the problem-specific scientific checkpoint `homerquan/DrugClip`, loaded by the BioTarget adapter as `best.ckpt`. `mirrorneuron-use-generic-model-skill` validates the explicit Hugging Face reference before the model-specific adapter downloads the matching checkpoint and instantiates native `DrugCLIP`. DrugClip is never added to the shared LLM model list, and Docker Model Runner is intentionally not used because this repository is not a DMR-compatible generative model. Its 3D graph and text encoders provide the BioTarget Stage C selection and Stage D toxicity-alignment path; live runs fail rather than substitute a synthetic model or score.

## NVIDIA CUDA requirement

The manifest hard-requires one NVIDIA CUDA GPU. MirrorNeuron resource validation owns the hardware check and rejects Apple-Silicon and CPU-only nodes before scheduling a workflow. Every specialist node uses one shared `MirrorNeuron.Runner.DockerWorker` configured with `gpus: all`; DockerWorker placement therefore also requires an NVIDIA node. Its CUDA/cuDNN image installs the SDK and agent dependencies, the native DrugClip stack, and GNINA `v1.3.2` for the selected GPU architecture. The native DrugClip adapter repeats that requirement at model load time by rejecting a PyTorch runtime without CUDA; it never falls back to CPU execution.

## Native cross-box contract

Target discovery, structure generation, candidate generation, binding review, and reporting run in the shared NVIDIA `DockerWorker`. The worker owns the continuous service and all real DrugClip/GNINA calls with the full `payloads/requirements.txt` stack plus the manifest-declared SDK and agent dependencies. Live cluster mode requires a native dispatcher command. The controller sends it a JSON job containing adapter name, target pool, expanded command, request path, output path, and request payload. BioTarget is bundled in `payloads/biotarget/`; the staged payload is preferred over any external source path. The dispatcher returns a JSON `result` or writes the output path. Missing dispatcher, bundled BioTarget package, checkpoint, GNINA binary, or adapter configuration is a live-run error.

## Service lifecycle

The service has no automatic completion time. It stops on a process termination signal or when the configured `STOP` file is created. Each cycle updates `service_state.json`; detailed artifacts are written under `cycles/cycle-<id>/`, while the configured user-facing output folder is updated with `service_status.json`, `candidates.json`, and `latest_cycle_report.json` so a long-running job has observable output before it stops.

## Safety and non-goals

All results are computational hypotheses. The blueprint does not synthesize compounds, run assays, make clinical claims, submit regulatory material, or send candidates to external systems. Fake adapters are limited to explicit mock/smoke-test configuration and are labeled synthetic in every artifact. BioTarget Stage D invokes the native GNINA executable in the selected NVIDIA DockerWorker; no nested Docker socket or CPU-emulation path is part of the live contract.
