# Research Co-Scientist

`Blueprint ID:` `research_coscientist`  
`Category:` `Science`

Research Co-Scientist turns a research goal and an approved evidence folder into a source-grounded research packet. Deterministic host stages normalize inputs, build the evidence ledger, and verify the final packet. A single shared OpenShell worker owns every autonomous phase: it may refine the goal, create phase prompts, call allowlisted `mn-skills` tools on demand, generate and execute bounded analysis code, challenge hypotheses, and draft the candidate packet.

It is inspired by the role separation in Google's AI co-scientist—not a reproduction of Google's system. The workflow uses an explicit evidence ledger and bounded review roles so that generated hypotheses remain hypotheses until a qualified person evaluates them.

## Quick Start

```bash
mn run research_coscientist
```

The default output folder is `~/Downloads/research_coscientist`. Run-store artifacts are also written under `~/.mn/runs/<run_id>/`.

The workflow deliberately mixes execution modes. `frame_research_problem` and
`build_research_evidence` prepare deterministic context;
`develop_and_challenge_hypotheses` contains the only OpenShell specialist; and
`verify_and_publish_research_packet` performs deterministic audit and report
publication. The autonomous worker uses the runtime's job-scoped shared sandbox
(`reuse_shared_sandbox: true`) for its bounded subphases. Generated code never
runs in a deterministic specialist.

## Process and agents

1. `research_goal_framer` normalizes the question, constraints, success criteria, and explicit unknowns.
2. `research_evidence_curator` creates the local/public evidence ledger and keeps run metadata separate from evidence.
3. `autonomous_researcher` develops hypotheses, counterarguments, predictions, disconfirming observations, and experiment concepts inside OpenShell.
4. `research_packet_auditor` verifies isolation trace, source refs, falsifiability, counterarguments, and review boundaries; `research_report_writer` then durably publishes the packet.

The bundled baseline CSV contains 12 synthetic cooling-loop observations so
the sample can form a measurable hypothesis rather than a generic prose idea.

## Inputs

- `research_goal`: required outcome, mechanism, or problem to investigate.
- `research_domain`, `research_question`, and `scope`: optional framing and boundaries.
- `success_criteria` and `constraints`: evaluation rules, safety/ethics boundaries, and required review gates.
- `seed_hypotheses`: optional human-provided starting ideas that the workflow must challenge, not endorse automatically.
- `input_folder`: local papers, notes, datasets, and evidence approved for the run. The bundled `examples/sample_inputs` folder is available in every workflow worker; provide an absolute path for your own material.
- `output_folder`: destination for the research packet and supporting ledgers.

The bundled sample is an engineering question about reducing energy use in a small data-center cooling loop. It is deliberately limited to desk research and experiment planning; it does not modify a live cooling system.

## Research Roles

The blueprint assigns bounded responsibilities across a topic finder, literature reviewer, idea generator, skeptic, proximity/novelty reviewer, experiment designer, code and benchmark planners, result analyst, paper writer, and meta-reviewer. Each role preserves evidence references or marks an assertion as an inference, hypothesis, or unknown.

Public research is limited to sanitized research goals and questions. It does not send private documents, credentials, participant data, or raw confidential notes to public search. Blocked pages, login walls, CAPTCHAs, stale sources, and evidence conflicts are recorded rather than bypassed.

## Outputs

The output folder contains:

- `research_packet.json` — goal, evidence, ranked hypotheses, critiques, experiment concepts, and review boundary.
- `research_brief.md` — readable draft of the same packet.
- `evidence_ledger.json` — local and public source records, status, and retrieval time.
- `hypothesis_ledger.json` — candidate hypotheses, predictions, counterarguments, and ranking posture.
- `review_ledger.json` — human-review and blocked-action status.
- `artifact_quality.json` and `run_health.json` — artifact and run checks.

Packets with at least one extracted local document or observed public source are `review_ready`. If neither is available, the full diagnostic bundle is still written, but the packet and quality report are marked `needs_evidence`; its next steps tell the customer whether to supply local material or retry retrieval. Run metadata is tracked separately from evidence references and never qualifies a packet as source-grounded.

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

## Validation

```bash
.venv/bin/python -m pytest -q
```
