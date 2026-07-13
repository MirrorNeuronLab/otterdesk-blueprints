# Research Co-Scientist

`Blueprint ID:` `research_coscientist`  
`Category:` `Science`

Research Co-Scientist turns a research goal and an approved evidence folder into a review-ready research packet. Deterministic host stages normalize inputs, build the evidence ledger, and verify the final packet. A single shared OpenShell worker owns every autonomous phase: it may refine the goal, create phase prompts, call allowlisted `mn-skills` tools on demand, generate and execute bounded analysis code, challenge hypotheses, and draft the candidate packet.

It is inspired by the role separation in Google's AI co-scientist—not a reproduction of Google's system. The workflow uses an explicit evidence ledger and bounded review roles so that generated hypotheses remain hypotheses until a qualified person evaluates them.

## Quick Start

```bash
mn run research_coscientist
```

The default output folder is `~/Download/research_coscientist`. Run-store artifacts are also written under `~/.mn/runs/<run_id>/`.

The workflow deliberately mixes execution modes. `prepare_research_context` and `verify_and_publish_packet` are deterministic HostLocal stages. `autonomous_research` is the only OpenShell node and uses the runtime's job-scoped shared sandbox (`reuse_shared_sandbox: true`) for all autonomous subphases. Generated code never runs in either deterministic stage.

## Inputs

- `research_goal`: required outcome, mechanism, or problem to investigate.
- `research_domain`, `research_question`, and `scope`: optional framing and boundaries.
- `success_criteria` and `constraints`: evaluation rules, safety/ethics boundaries, and required review gates.
- `seed_hypotheses`: optional human-provided starting ideas that the workflow must challenge, not endorse automatically.
- `input_folder`: local papers, notes, datasets, and evidence approved for the run.
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

The blueprint does not run unapproved experiments, make a validated scientific or clinical claim, publish or submit a manuscript, contact research participants, or make consequential safety decisions. A person must review and approve any such action.

## Validation

```bash
.venv/bin/python -m pytest -q
```
