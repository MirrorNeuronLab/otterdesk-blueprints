# Research Co-Scientist v2 SPEC

## Purpose

Provide a source-grounded, adversarial research workflow for scientists, engineers, analysts, and research leads. The workflow turns a research goal plus approved local evidence into a research brief with ranked hypotheses, competing explanations, evidence gaps, test concepts, and review-only next steps.

## Workflow

1. Frame the goal as answerable questions, scope, success criteria, assumptions, and unknowns.
2. Read approved local papers, notes, datasets, and evidence through direct extraction or OCR.
3. Retrieve checked-in research-method guidance and local evidence in an isolated run context.
4. Perform bounded public research from sanitized goal and question text, recording sources, retrieval timestamps, access failures, and warnings.
5. Generate candidate hypotheses; challenge them through skeptical reflection, proximity/novelty review, and explicit evidence ranking.
6. Draft experiment, code, benchmark, and result-analysis plans. A meta-reviewer audits the packet before it is released for human review.

The roles are inspired by the generation, reflection, ranking, evolution, proximity, and meta-review pattern described for Google's AI co-scientist. This blueprint uses those ideas as a workflow pattern; it does not claim to replicate Google's models, data, or results.

## Output Contract

The primary artifact is `mn.blueprint.research_coscientist.v2`. It contains a research goal, executive summary, `recommended_action` (`review_research_packet` or `gather_more_evidence`), confidence, source-grounded evidence, autonomous session and generated-code traces, a hypothesis ledger, critique ledger, experiment concepts, evidence gaps, next steps, and source references. Its `status` is `review_ready` only when at least one extracted local document or observed public source is present; otherwise it is `needs_evidence` and preserves diagnostics without presenting the packet as review-ready.

The workflow has three execution stages: deterministic context preparation, one isolated autonomous OpenShell worker, and deterministic verification/publication. The OpenShell worker may set or refine goals, create prompts, request allowlisted `mn-skills` tools, and execute validated generated Python. All such actions must appear in the autonomous session ledger. The final deterministic stage rejects untraceable claims or missing review boundaries.

Each hypothesis must identify its mechanism, predicted observation, evidence support, counterarguments, and what would disconfirm it. Novelty and causal claims are always bounded assessments, never guarantees. The generated brief is a draft, not a paper or validated scientific result.

## Research Boundaries

Public queries contain only sanitized research-goal, domain, and question text. Login walls, robots restrictions, CAPTCHAs, rate limits, conflicts, and unavailable sources are retained as warnings. The workflow never bypasses access controls, contacts participants, collects restricted data, changes live systems, executes an experiment, or submits a manuscript.

For medical, biological, safety-critical, or regulated topics, users must supply the applicable human oversight, ethics, institutional, and domain-expert review. The workflow is not clinical advice and must not be used to make treatment, diagnostic, or safety decisions.

## Evaluation

- Source records preserve origin, retrieval time, access status, and warnings; run metadata is provenance, not evidence.
- Facts, inferences, hypotheses, and unknowns remain distinct.
- Candidate hypotheses are falsifiable and include a counterargument or disconfirming observation.
- Experiment and benchmark concepts name controls, measurements, decision rules, and approval dependencies.
- Missing, stale, blocked, and conflicting evidence is explicit.
- Fake/offline runs are deterministic and write the full output bundle.
- Consequential actions remain blocked pending human review.
