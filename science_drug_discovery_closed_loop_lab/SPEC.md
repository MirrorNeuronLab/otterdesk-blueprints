# Drug Discovery Closed Loop Lab SPEC

## What We Want To Achieve

Build an auditable scientific discovery loop that repeatedly moves from an initial disease or target question to ranked candidate hypotheses. The target customer should be able to trace each candidate through the stages that produced it and decide what deserves expert review or follow-up experimentation.

## Customer Problem

Computational biology researchers and scientific AI platform evaluators need a repeatable loop for generating, evaluating, and ranking candidate hypotheses. The customer gap is traceability across stages: targets, structures, generated candidates, evaluations, and review summaries must remain connected as evidence changes.

## Design Details

The blueprint is organized as a staged worker graph. `target_discovery` emits `targets_ready`, `structure_generation` emits `structures_ready`, `candidate_generation` emits `candidates_ready`, `binding_evaluation` emits `evaluations_ready`, and `ranking_reporting` emits the final ranked result.

A manager monitor observes the stage outputs so the workflow can be reviewed as a connected discovery trace rather than as disconnected scripts. The design goal is to preserve stage-level provenance when replacing prototype workers with validated scientific models and lab adapters.

## Input

The prototype starts with a disease or target discovery seed input and passes staged worker context through target discovery, structure generation, candidate generation, binding evaluation, and ranking/reporting. Intermediate inputs include generated targets, structure artifacts, candidate molecules or representations, evaluation outputs, and stage-specific worker messages.

For production use, the same contract should be fed by scientific datasets, literature retrieval, validated target databases, structure predictors, candidate generators, docking or scoring models, assay results, lab automation outputs, and expert review decisions.

## Output: Expected Customer Outcome

The expected customer outcome is an auditable multi-stage discovery loop that repeatedly produces and ranks candidate hypotheses for expert review. A useful run returns candidate artifacts, stage logs, ranked candidate summaries, discovery trace, and evidence showing how each candidate moved from disease or target input through evaluation.

The customer should be able to answer which targets were considered, which structures or candidates were generated, how candidates were evaluated, which candidates ranked best, and what evidence supports the next scientific review step.

## Evaluation Criteria

- Stage completion: verify each pipeline stage emits the expected message type and required payload for the next stage.
- Candidate validity: check that generated candidates are syntactically and scientifically plausible for the configured workflow.
- Scoring consistency: confirm rankings follow the evaluation scores and do not lose successful candidates.
- Traceability: verify disease, gene or target, structure, candidate, and evaluation records can be linked end to end.
- Artifact integrity: confirm generated files, logs, and summaries are present, readable, and tied to the run.
- Reproducibility: run deterministic or mock paths where available and confirm stable outputs for the same seed or input.
- Scientific usefulness: have domain reviewers judge whether the ranked candidates and evidence are credible enough to prioritize follow-up experiments.

## Result Artifacts To Inspect

Inspect worker messages for `targets_ready`, `structures_ready`, `candidates_ready`, `evaluations_ready`, and `pipeline_complete`. Inspect stage logs for errors, skipped records, extraction issues, and ranking decisions.

Inspect final candidate summaries and generated files such as ranked candidate reports or best-candidate records. When using the standard local run store, inspect `run.json`, `config.json`, `inputs.json`, `events.jsonl`, `result.json`, and `final_artifact.json` if produced by the runtime path.

## Prototype Limits

The current blueprint is an early prototype with simplified staged workers and bundled or mock-style inputs. It is intended for workflow evaluation and platform demonstration, not validated drug discovery or clinical decision-making.

Scientific assumptions, model quality, target validity, docking reliability, assay relevance, safety, novelty, and intellectual-property constraints must be validated before any real research program depends on the output.

## Upgrade Path To Real Customer Use

Connect validated scientific data sources, structure tools, candidate generation models, docking or binding evaluation systems, assay result adapters, and lab workflow systems. Preserve stage-level provenance so every candidate can be traced back to its source evidence.

Add domain-specific quality gates, expert review steps, stopping criteria, experiment prioritization, and feedback from real assays. Track candidate validity, reviewer acceptance, cycle-time reduction, hit-rate improvement, reproducibility, and evidence traceability across repeated discovery loops.
