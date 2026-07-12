# Drug Discovery Research Assistant

`Blueprint ID:` `drug_discovery_research_assistant`

`Category:` `Science`
`Mode:` continuous service, manually stopped

This blueprint runs a review-only discovery service until it is closed manually. Each cycle uses the local BioTarget Stage C path to generate a molecular candidate pool and rank it against therapeutic text with DrugClip, folds targets, runs BioTarget evaluation, and writes traceable cycle artifacts for human scientific review.

`hf.co/homerquan/DrugClip` is declared under `runtime.models.drugclip` with `customize_mode: true`. It is your dual-encoder text↔3D-molecular-graph model: BioTarget generates the candidate pool, then DrugClip aligns each molecular graph with therapeutic intent and toxicity text. Live workers load the model through the BioTarget Python package and the `best.ckpt` checkpoint from the Hugging Face repository.

## Running and stopping

Start the service with:

```bash
mn run drug_discovery_research_assistant
```

The service continues until the runtime sends `SIGTERM`/`SIGINT` or the configured `STOP` file is created under the run directory. It writes `service_state.json` and per-cycle artifacts under `cycles/` while it runs.

The committed `config/overwrite.json` keeps the service in explicit fake-science mode for a continuous local smoke run. To make a bounded test, provide `service.max_cycles` through the runtime override. Live use must set `mode` to `live`, disable `execution.fake_science_adapters`, configure the native adapter commands, and configure the cross-box dispatcher.

## Distributed native execution

The service coordinator and BioTarget adapter jobs use `MirrorNeuron.Runner.HostLocal`, not OpenShell. In live cluster mode, it sends JSON job specifications to a configured native dispatcher that places work in these pools:

- `science-generation`: candidate-generation jobs
- `science-folding`: fan-out folding by target
- `science-drugclip`: fan-out DrugCLIP target–candidate screening
- `science-simulation`: fan-out simulation of DrugCLIP-selected candidates
- `default`: native control, aggregation, state, and review reports

The dispatcher must accept the job JSON on stdin and return a JSON result or write the declared output file. If it is absent, live runs fail closed rather than running a misleading local fallback. BioTarget Stage D currently uses its own GNINA containerized runner for docking; this is isolated to the scientific evaluation adapter, while the service control plane remains native.

## Output and safety

The default user-facing output folder is `~/Downloads/drug_discovery_research_assistant`. Service reports are computational hypotheses only. The blueprint does not authorize wet-lab work, clinical claims, regulatory submissions, or external candidate publication without human approval.

## Validation

```bash
python3 -m pytest -q tests/test_drug_discovery_research_assistant.py
```
