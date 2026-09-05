# Drug Discovery Research Assistant

`Blueprint ID:` `drug_discovery_research_assistant`

`Category:` `Science`
`Mode:` batch: one cycle, five distinct candidates

This blueprint runs one review-only discovery cycle and then completes all five workflow steps. It returns five distinct molecules, retaining each molecule's best screened target for evaluation. The cycle uses the local BioTarget Stage C path to generate a molecular candidate pool and rank it against therapeutic text with DrugClip, folds targets, runs BioTarget evaluation, and writes traceable cycle artifacts for human scientific review.

OtterDesk also exposes a read-only **Drug Discovery Progress** web UI. It renders the leading simulation-ranked candidate as a local 2D molecule diagram with its SMILES string and bounded DrugCLIP, stability, GNINA-affinity, and toxicity scores. The same view shows the five logical workflow steps separately from the five phases inside the current discovery cycle, along with bounded target, candidate, screen, simulation, and completed-cycle counts. The UI reads durable artifacts and workflow events; it cannot start a run, stop the service, approve a candidate, or invoke a scientific adapter.

The web UI is an auxiliary runtime entrypoint. Manifest expansion starts it alongside the compiler-generated `target_discovery__start` workflow root, so UI supervision cannot replace or block the first scientific step.

DrugClip is a problem-specific scientific checkpoint, not a shared LLM model. The adapter uses `mirrorneuron-use-generic-model-skill` to validate the explicit `https://huggingface.co/homerquan/DrugClip` reference, then downloads `best.ckpt` and runs it through the native `DrugCLIP` graph/text adapter. Docker Model Runner is deliberately not used for DrugClip: the repository is a checkpoint-only graph/text model, not a DMR-compatible generative model. No fake adapter or surrogate score is used in live mode.

The explanatory LLM actors use Docker Model Runner's logical `default` route through `api_base: auto`. The blueprint does not pin a concrete shared LLM or `runtime_model`; runtime model selection remains with the platform and the operator-selected default. This routing is independent of the native DrugClip checkpoint.

This blueprint hard-requires at least one schedulable NVIDIA CUDA GPU with at least 48 GB (49,152 MB) of memory. The manifest declares this before scheduling, so the platform rejects Apple-Silicon, CPU-only, and undersized placements before a workflow is submitted. Every specialist step runs in one shared `DockerWorker` with `gpus: all`; that image contains the SDK and agent runtime, CUDA/cuDNN, the real DrugClip dependencies, and a native GNINA build. The image pins PyTorch to the CUDA-13-compatible 2.12 line because GNINA v1.3.2 compiles its C++ integration as C++17; unbounded newer PyTorch releases require C++20 headers and cannot be compiled into that pinned GNINA release. The native DrugClip adapter also rejects a CPU-only PyTorch installation rather than silently falling back to CPU execution.

## Running

Start the batch with:

```bash
cd drug_discovery_research_assistant
mn blueprint run .
```

The discovery stage runs exactly once, including when an older override contains `service.max_cycles: null`. It then returns five evaluated molecules to Cycle Results Review and Ranking And Reporting. The generated workflow terminal completes the batch after the final report is written. If fewer than five distinct valid molecules are available, the run fails explicitly.

Open the **Drug Discovery Progress** output in OtterDesk to follow:

1. Target Discovery
2. Structure Generation
3. Discover Five Candidates
4. Cycle Results Review
5. Ranking And Reporting

During step 3, the same UI shows candidate generation, target folding, DrugCLIP screening, GNINA/toxicity evaluation, and cycle-report publication as distinct live phases. After ranking, the Docker worker uses its declared RDKit dependency to generate `leading_candidate.svg`; the job-scoped web service serves that artifact directly without an external chemistry or rendering service. `cycle_progress.json` is updated atomically in both the run store and configured output folder, so a refresh never needs to parse a partially written progress document.

The committed `config/overwrite.json` selects live native adapter mode. On the first model-dependent adapter call, the generic-model skill validates the configured `https://huggingface.co/homerquan/DrugClip` reference without adding it to the shared model catalog; the native adapter then loads `best.ckpt` from the same repository when it is not cached. The BioTarget source is bundled under `payloads/biotarget/`, and its native dependencies are declared in `payloads/requirements.txt`; no external BioTarget checkout is required. The DockerWorker builds its native GNINA executable from the pinned `v1.3.2` source release, and the Open Targets/AlphaFold network APIs remain external live-run requirements. The batch always runs one cycle; `service.max_cycles` cannot enable continuous execution. Fake adapters are limited to explicit mock/smoke-test overrides.

## Distributed native execution

The target, structure, candidate-generation, binding-review, and report specialists use one shared `MirrorNeuron.Runner.DockerWorker` on the NVIDIA CUDA node. Its full `payloads/requirements.txt` DrugClip/GNINA stack and the declared SDK/agent dependencies execute in the prepared GPU container rather than an isolated HostLocal environment. This single-worker mode is the live default, so it needs no cross-box dispatcher. The native adapter commands intentionally use the active `python` executable (not `/usr/bin/python3`) so they use the Docker worker's `/opt/mn-venv`, where DrugClip and CUDA PyTorch are installed.

Cross-box dispatch is an optional advanced configuration. When `cluster_distribution.enabled` is explicitly set to `true`, the discovery worker sends JSON job specifications to a configured native dispatcher that places work in these pools:

- `science-generation`: candidate-generation jobs
- `science-folding`: fan-out folding by target
- `science-drugclip`: fan-out DrugCLIP target–candidate screening
- `science-simulation`: fan-out simulation of DrugCLIP-selected candidates
- `default`: native control, aggregation, state, and review reports

The dispatcher must accept the job JSON on stdin and return a JSON result or write the declared output file. If it is absent, live runs fail closed rather than running a misleading local fallback. BioTarget Stage D invokes the GNINA binary already installed in the GPU DockerWorker image; it never relies on a nested Docker socket.

## Output and safety

The default user-facing output folder is `~/Downloads/{job_name}`. While the service runs, it publishes `service_status.json`, `cycle_progress.json`, the latest generated candidate pool in `candidates.json`, the latest completed cycle in `latest_cycle_report.json`, and the leading-candidate view in `leading_candidate.json` plus `leading_candidate.svg`; detailed per-cycle artifacts remain under the run directory. Only that single leading candidate is projected into the web UI—the full candidate pool and private input text remain outside its state response. Service reports are computational hypotheses only. The blueprint does not authorize wet-lab work, clinical claims, regulatory submissions, or external candidate publication without human approval.

## Shared job data

The configured research job seeds bundled knowledge once, then shares
`knowledge/`, `databases/rag/`, and `state/` across runs without overwriting
edits. Experimental inputs, outputs, logs, and artifacts remain isolated by
`run_id`.

## Persistent conversation

OtterDesk can ask this hired co-worker about its scientific role, schedule,
latest cycle, or review gates through the stable Job response service even while
the discovery worker is stopped. Conversation never starts a discovery
cycle.

## Validation

```bash
python3 -m pytest -q tests/test_drug_discovery_research_assistant.py
```

Output folder `{job_name}` is resolved by the submission SDK to the configured job name, for example `~/Downloads/drug-discovery-research-assistant`. The SDK copies remote outputs back to this directory on the submitting host. `candidates.json` contains five unique molecules; `final_artifact.json` contains their ranked evaluations. The existing live run retains its submitted configuration; these settings apply to new runs.

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
