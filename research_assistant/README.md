# Research Assistant

`Blueprint ID:` `research_assistant`  
`Category:` `Science`

Research Assistant turns a research goal and an approved evidence folder into a source-grounded research packet. Deterministic stages normalize inputs, build the evidence ledger, and verify the final packet. A single shared Docker worker owns every autonomous phase: it may refine the goal, create phase prompts, call allowlisted `mn-skills` tools on demand, generate and execute bounded analysis code, challenge hypotheses, and draft the candidate packet.

The autonomous specialist receives its configured LLM through the same SDK-backed blueprint support client used by VC Assistant. The blueprint requests the logical `default` model and the runtime selects the concrete model automatically. Normal runs require live model-backed analysis and fail instead of silently publishing a deterministic fallback; quick tests remain deterministic.

Like VC Assistant, the blueprint declares `llm.model` as logical `default` and
does not declare a machine-specific model, endpoint, or placement. MirrorNeuron
owns model selection and routing; the payload only calls the configured actor
client supplied by the runtime.

It is inspired by the role separation in Google's AI co-scientist—not a reproduction of Google's system. The workflow uses an explicit evidence ledger and bounded review roles so that generated hypotheses remain hypotheses until a qualified person evaluates them.

## Quick Start

```bash
mn run research_assistant
```

The default output folder is `~/Downloads/research_assistant`. Run-store artifacts are also written under `~/.mn/runs/<run_id>/`.

Like VC Assistant, every executable specialist runs through the runtime's
shared Docker-worker path. `frame_research_problem` and
`build_research_evidence` prepare deterministic context;
`develop_and_challenge_hypotheses` runs the isolated autonomous specialist; and
`verify_and_publish_research_packet` performs deterministic audit and report
publication. The autonomous phases stay inside one job-scoped worker invocation.
Generated code never runs in a deterministic specialist.

## Process and agents

1. `research_goal_framer` normalizes the question, constraints, success criteria, and explicit unknowns.
2. `research_evidence_curator` creates the local/public evidence ledger and keeps run metadata separate from evidence.
3. `autonomous_researcher` performs a bounded, multi-pass research procedure inside the isolated Docker worker: source-by-source analysis; question decomposition; competing-hypothesis generation; a separate adversarial review for each hypothesis; gap-directed tool/code planning; evidence-based revision; experiment design; independent meta-review and ranking; and a final executive synthesis. It then sends the resulting packet through the configured specialist-role reviews.
4. `research_packet_auditor` verifies isolation trace, source refs, falsifiability, counterarguments, and review boundaries; `research_report_writer` then durably publishes the packet.

The bundled baseline CSV contains 12 synthetic robotics-simulation runs across
Isaac Sim, Gazebo, and MuJoCo so the sample can form measurable hypotheses
rather than generic prose ideas.

## Inputs

- `research_goal`: required outcome, mechanism, or problem to investigate.
- `research_domain`, `research_question`, and `scope`: optional framing and boundaries.
- `success_criteria` and `constraints`: evaluation rules, safety/ethics boundaries, and required review gates.
- `seed_hypotheses`: optional human-provided starting ideas that the workflow must challenge, not endorse automatically. A seed may be a statement string or a structured test contract with its prediction, counterargument, disconfirming observation, assumptions, relevant source refs, and experiment procedure.
- `input_folder`: local papers, notes, datasets, and evidence approved for the run. The bundled `examples/sample_inputs` folder is available in every workflow worker; provide an absolute path for your own material.
- `output_folder`: destination for the research packet and supporting ledgers.

The bundled sample evaluates shared robotics simulation infrastructure for
manipulation, navigation, and multi-robot teams. It is deliberately limited to
desk research and offline simulation planning; it does not modify live robots
or production simulators.

## Research Roles

The blueprint assigns bounded responsibilities across a topic finder, literature reviewer, idea generator, skeptic, proximity/novelty reviewer, experiment designer, code and benchmark planners, result analyst, paper writer, and meta-reviewer. Each role preserves evidence references or marks an assertion as an inference, hypothesis, or unknown.

Public research uses `web_browser_skill` standard mode, which starts with
lightweight w3m extraction and invokes its policy-governed rendered browser only
when needed. Queries are limited to sanitized research goals and questions. The
workflow does not send private documents, credentials, participant data, or raw
confidential notes to public search. Blocked pages, login walls, CAPTCHAs, stale
sources, and evidence conflicts are recorded rather than bypassed.

## Outputs

The output folder contains:

- `research_packet.json` — goal, evidence, ranked hypotheses, critiques, experiment concepts, and review boundary.
- `research_brief.md` — readable draft of the same packet.
- `evidence_ledger.json` — local and public source records, status, and retrieval time.
- `hypothesis_ledger.json` — candidate hypotheses, predictions, counterarguments, and ranking posture.
- `review_ledger.json` — human-review and blocked-action status.
- `artifact_quality.json` and `run_health.json` — artifact and run checks.

Packets with at least one extracted local document or observed public source are `review_ready`. If neither is available, the full diagnostic bundle is still written, but the packet and quality report are marked `needs_evidence`; its next steps tell the customer whether to supply local material or retry retrieval. Run metadata is tracked separately from evidence references and never qualifies a packet as source-grounded.

The brief exposes the question decomposition, cross-source agreements and
tensions, the executed research procedure, per-hypothesis critiques and
rankings, and complete review-only test procedures with units, baselines,
outcomes, decision rules, analysis plans, and stop conditions. Generation
provenance records every model and fallback call plus the completed phase count.
Source links mean relevant context unless the source itself reports the
observation; they never validate a hypothesis.

The blueprint does not run unapproved experiments, make a validated scientific or clinical claim, publish or submit a manuscript, contact research participants, or make consequential safety decisions. A person must review and approve any such action.

## Shared job data

The stable research job seeds bundled knowledge once and reuses its
`knowledge/`, `databases/rag/`, and `state/` resources across runs. Hypothesis
inputs, evidence, and reports remain run-scoped; another job gets an independent
store.

## Payload layout

The four `payloads/steps/` modules declare only logical contracts and internal
agent graphs. Five same-named modules under `payloads/agents/` bind focused
implementations from `payloads/domain/inputs.py`, `evidence.py`,
`autonomous.py`, `verification.py`, and `reporting.py`. Runtime preparation is
isolated in `runtime_services.py`; local sample composition lives in
`composition.py`.

## Persistent conversation

OtterDesk can ask this hired co-worker about its research role, schedule,
latest hypotheses, or evidence gaps through the stable Job response service even
before its first run or while idle. Conversation never starts research or an
experiment.

## Validation

```bash
.venv/bin/python -m pytest -q
```

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
