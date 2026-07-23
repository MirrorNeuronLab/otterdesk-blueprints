# Research Co-Scientist v2 SPEC

## Purpose

Provide a source-grounded, adversarial research workflow for scientists, engineers, analysts, and research leads. The workflow turns a research goal plus approved local evidence into a research brief with ranked hypotheses, competing explanations, evidence gaps, test concepts, and review-only next steps.

## Workflow

1. `frame_research_problem`: `research_goal_framer` turns the goal into answerable questions, scope, criteria, assumptions, and unknowns.
2. `build_research_evidence`: `research_evidence_curator` reads approved local sources, retrieves checked-in guidance, and records bounded public evidence with timestamps and access status.
3. `develop_and_challenge_hypotheses`: the isolated `autonomous_researcher` generates candidates, counterarguments, disconfirming observations, and experiment/code/benchmark concepts.
4. `verify_and_publish_research_packet`: `research_packet_auditor` enforces deterministic release checks before `research_report_writer` publishes the packet.

The roles are inspired by the generation, reflection, ranking, evolution, proximity, and meta-review pattern described for Google's AI co-scientist. This blueprint uses those ideas as a workflow pattern; it does not claim to replicate Google's models, data, or results.

## Output Contract

The primary artifact is `mn.blueprint.research_coscientist.v2`. It contains a research goal, executive summary, `recommended_action` (`review_research_packet` or `gather_more_evidence`), confidence, source-grounded evidence, autonomous session and generated-code traces, a hypothesis ledger, critique ledger, experiment concepts, evidence gaps, next steps, and source references. Its `status` is `review_ready` only when at least one extracted local document or observed public source is present; otherwise it is `needs_evidence` and preserves diagnostics without presenting the packet as review-ready.

The workflow has four logical steps spanning three execution modes: deterministic context preparation, one isolated autonomous OpenShell worker, and deterministic verification/publication. The OpenShell worker may set or refine goals, create prompts, request allowlisted `mn-skills` tools, and execute validated generated Python. All such actions must appear in the autonomous session ledger. The final deterministic step rejects untraceable claims or missing review boundaries.

Each hypothesis must identify its mechanism, predicted observation, evidence support, counterarguments, and what would disconfirm it. Novelty and causal claims are always bounded assessments, never guarantees. The generated brief is a draft, not a paper or validated scientific result.

## Research Boundaries

Public queries contain only sanitized research-goal, domain, and question text. Login walls, robots restrictions, CAPTCHAs, rate limits, conflicts, and unavailable sources are retained as warnings. The workflow never bypasses access controls, contacts participants, collects restricted data, changes live systems, executes an experiment, or submits a manuscript.

For medical, biological, safety-critical, or regulated topics, users must supply the applicable human oversight, ethics, institutional, and domain-expert review. The workflow is not clinical advice and must not be used to make treatment, diagnostic, or safety decisions.

## Persistent job data

Persistent knowledge, Milvus Lite data, and durable state belong to the stable
`job_id`. They survive run completion and cancellation; only explicit data
reset or confirmed job deletion clears them.

## Evaluation

- Source records preserve origin, retrieval time, access status, and warnings; run metadata is provenance, not evidence.
- Facts, inferences, hypotheses, and unknowns remain distinct.
- Candidate hypotheses are falsifiable and include a counterargument or disconfirming observation.
- Experiment and benchmark concepts name controls, measurements, decision rules, and approval dependencies.
- Missing, stale, blocked, and conflicting evidence is explicit.
- Fake/offline runs are deterministic and write the full output bundle.
- Consequential actions remain blocked pending human review.
