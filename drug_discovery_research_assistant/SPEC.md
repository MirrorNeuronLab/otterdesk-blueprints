# Drug Discovery Research Assistant Service SPEC

## Purpose

Operate a continuously running, human-review-only computational discovery service. It uses the local BioTarget pipeline and `homerquan/DrugClip` text↔molecular-graph model to produce and prioritize candidate hypotheses, runs folding and simulation adapters, and retains cycle-level evidence until an operator manually stops the service.

## Scientific pipeline

1. BioTarget Stage C builds a molecular candidate pool and uses DrugClip graph-text alignment to select candidate hypotheses for the configured therapeutic text.
2. Folding fans out by target across the `science-folding` pool.
3. DrugCLIP fans out target–candidate screening across the `science-drugclip` pool.
4. Simulations fan out over the best DrugCLIP-ranked candidates across the `science-simulation` pool.
5. The native control worker fans results in, writes a cycle report, and starts the next cycle.

DrugClip is the native scientific checkpoint `homerquan/DrugClip`, loaded by the BioTarget adapter as `best.ckpt`. Its 3D graph and text encoders provide the BioTarget Stage C selection and Stage D toxicity-alignment path; it is not a Docker Model Runner chat model. Docker Model Runner is limited to the blueprint's LLM and retrieval models.

## Native cross-box contract

The service controller is a `MirrorNeuron.Runner.HostLocal` worker. Live cluster mode requires a native dispatcher command. The controller sends it a JSON job containing adapter name, target pool, expanded command, request path, output path, and request payload. The payload carries the BioTarget source and DrugClip checkpoint configuration. The dispatcher returns a JSON `result` or writes the output path. Missing dispatcher, BioTarget source, checkpoint, or adapter configuration is a live-run error.

## Service lifecycle

The service has no automatic completion time. It stops on a process termination signal or when the configured `STOP` file is created. Each cycle updates `service_state.json`; artifacts are written under `cycles/cycle-<id>/`.

## Safety and non-goals

All results are computational hypotheses. The blueprint does not synthesize compounds, run assays, make clinical claims, submit regulatory material, or send candidates to external systems. Fake adapters are limited to explicit mock/smoke-test configuration and are labeled synthetic in every artifact. BioTarget Stage D's current GNINA invocation is containerized; the control service and cross-box adapters are native workers.
