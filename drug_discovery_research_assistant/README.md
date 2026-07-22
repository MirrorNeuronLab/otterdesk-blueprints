# Drug Discovery Research Assistant

`Blueprint ID:` `drug_discovery_research_assistant`

`Category:` `Science`
`Mode:` continuous service, manually stopped

This blueprint runs a review-only discovery service until it is closed manually. Each cycle uses the local BioTarget Stage C path to generate a molecular candidate pool and rank it against therapeutic text with DrugClip, folds targets, runs BioTarget evaluation, and writes traceable cycle artifacts for human scientific review.

DrugClip is a problem-specific scientific checkpoint, not a shared LLM model. The adapter uses `mirrorneuron-use-generic-model-skill` to validate the explicit `https://huggingface.co/homerquan/DrugClip` reference, then downloads `best.ckpt` and runs it through the native `DrugCLIP` graph/text adapter. Docker Model Runner is deliberately not used: the repository is a checkpoint-only graph/text model, not a DMR-compatible generative model. No fake adapter or surrogate score is used in live mode.

This blueprint requires one NVIDIA CUDA GPU. The manifest declares that as a hard runtime requirement, so the platform rejects Apple-Silicon and CPU-only nodes before a workflow is submitted. Every specialist step runs in one shared `DockerWorker` with `gpus: all`; that image contains the SDK and agent runtime, CUDA/cuDNN, the real DrugClip dependencies, and a native GNINA build. The native DrugClip adapter also rejects a CPU-only PyTorch installation rather than silently falling back to CPU execution.

## Running and stopping

Start the service with:

```bash
mn run drug_discovery_research_assistant
```

The service continues until the runtime sends `SIGTERM`/`SIGINT` or the configured `STOP` file is created under the run directory. It writes `service_state.json` and per-cycle artifacts under `cycles/` while it runs.

The committed `config/overwrite.json` selects live native adapter mode. On the first model-dependent adapter call, the generic-model skill validates the configured `https://huggingface.co/homerquan/DrugClip` reference without adding it to the shared model catalog; the native adapter then loads `best.ckpt` from the same repository when it is not cached. The BioTarget source is bundled under `payloads/biotarget/`, and its native dependencies are declared in `payloads/requirements.txt`; no external BioTarget checkout is required. The DockerWorker builds its native GNINA executable from the pinned `v1.3.2` source release, and the Open Targets/AlphaFold network APIs remain external live-run requirements. To run a bounded test, provide `service.max_cycles` through the runtime override. Fake adapters are limited to explicit mock/smoke-test overrides.

## Distributed native execution

The target, structure, candidate-generation, binding-review, and report specialists use one shared `MirrorNeuron.Runner.DockerWorker` on the NVIDIA CUDA node. Its full `payloads/requirements.txt` DrugClip/GNINA stack and the declared SDK/agent dependencies execute in the prepared GPU container rather than an isolated HostLocal environment. In live cluster mode, the continuous service sends JSON job specifications to a configured native dispatcher that places work in these pools:

- `science-generation`: candidate-generation jobs
- `science-folding`: fan-out folding by target
- `science-drugclip`: fan-out DrugCLIP target–candidate screening
- `science-simulation`: fan-out simulation of DrugCLIP-selected candidates
- `default`: native control, aggregation, state, and review reports

The dispatcher must accept the job JSON on stdin and return a JSON result or write the declared output file. If it is absent, live runs fail closed rather than running a misleading local fallback. BioTarget Stage D invokes the GNINA binary already installed in the GPU DockerWorker image; it never relies on a nested Docker socket.

## Output and safety

The default user-facing output folder is `~/Downloads/drug_discovery_research_assistant`. While the service runs, it publishes `service_status.json`, the latest generated candidate pool in `candidates.json`, and the latest completed cycle in `latest_cycle_report.json`; detailed per-cycle artifacts remain under the run directory. Service reports are computational hypotheses only. The blueprint does not authorize wet-lab work, clinical claims, regulatory submissions, or external candidate publication without human approval.

## Validation

```bash
python3 -m pytest -q tests/test_drug_discovery_research_assistant.py
```
