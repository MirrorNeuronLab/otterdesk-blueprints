# Drug Discovery Closed Loop Lab

`Blueprint ID:` `science_drug_discovery_closed_loop_lab`  
`Category:` science - Science Solution Template  
`Default LLM:` Ollama `nemotron3:33b` with deterministic fake LLM support for tests

## Intro

Drug Discovery Closed Loop Lab is an early MirrorNeuron blueprint for running a staged scientific discovery workflow. It demonstrates how target discovery, structure generation, candidate generation, binding evaluation, and ranking can be connected into an auditable loop.

This README is the short product introduction. The detailed design contract, expected customer outcome, inputs, outputs, and evaluation criteria live in [SPEC.md](SPEC.md).

## Who It Serves

This blueprint is for computational biology researchers and scientific AI platform evaluators who need repeatable candidate-generation workflows with traceable evidence across stages.

## What It Demonstrates

- Long-running scientific pipeline orchestration.
- Multi-stage worker flow from disease input to ranked candidates.
- Candidate artifact extraction and stage logging.
- Reviewable trace from initial scientific question to final candidate summary.

## Example Scenario

A disease seed such as Alzheimer starts the workflow. Staged workers generate target data, structures, candidate molecules, binding evaluations, and a final ranked summary for expert review.

## Quick Start

Run through a registered MirrorNeuron blueprint checkout:

```bash
mn blueprint run science_drug_discovery_closed_loop_lab
```

Inspect registered blueprints and recent run artifacts through the unified CLI:

```bash
mn blueprint list
mn blueprint monitor
```

## Documentation Map

- [SPEC.md](SPEC.md): design details, desired customer outcome, input/output contract, evaluation criteria, prototype limits, and upgrade path.
- `manifest.json`: runtime graph, staged worker nodes, edges, initial inputs, and metadata.
- `config/default.json`: default identity, inputs, LLM, output, logging, and adapter settings.
- `payloads/worker/`: staged worker scripts and extraction utilities.

## Prototype Status

This blueprint is a working prototype for evaluating closed-loop scientific workflow design. It is not a validated discovery platform until connected to real scientific data, validated models, lab results, and expert review gates.
