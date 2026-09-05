# Research Assistant v2 SPEC

## Purpose

Provide a source-grounded, adversarial research workflow for scientists, engineers, analysts, and research leads. The workflow turns a research goal plus approved local evidence into a research brief with ranked hypotheses, competing explanations, evidence gaps, test concepts, and review-only next steps.

## Workflow

1. `frame_research_problem`: `research_goal_framer` turns the goal into answerable questions, scope, criteria, assumptions, and unknowns.
2. `build_research_evidence`: `research_evidence_curator` reads approved local sources, retrieves checked-in guidance, and records bounded public evidence with timestamps and access status.
3. `develop_and_challenge_hypotheses`: the isolated `autonomous_researcher` reads and assesses each bounded source excerpt, decomposes the question, generates genuinely competing candidates, runs a separate adversarial review for each candidate, plans gap-directed probes, revises against observations, designs complete tests, independently ranks the surviving hypotheses, and writes a final decision-oriented synthesis without introducing new evidence.
4. `verify_and_publish_research_packet`: `research_packet_auditor` enforces deterministic release checks before `research_report_writer` publishes the packet.

The roles are inspired by the generation, reflection, ranking, evolution, proximity, and meta-review pattern described for Google's AI co-scientist. This blueprint uses those ideas as a workflow pattern; it does not claim to replicate Google's models, data, or results.

The autonomous specialist uses the same configured SDK-backed LLM client and
action-budget wrapper as VC Assistant. The manifest requests model `default` so
the runtime selects the concrete model. Outside quick tests, every research
phase and specialist review must receive a live provider response; a fallback,
unavailable provider, or exhausted model-call budget fails the required step.
The blueprint follows VC Assistant's model contract: `llm.model` is logical
`default`, and payload code calls the configured actor client. The runtime owns
the concrete model, endpoint, preparation, and placement; blueprint code must
not replace them with machine-specific choices.

## Output Contract

The primary artifact is `mn.blueprint.research_assistant.v2`. It contains a research goal, executive summary, `recommended_action` (`review_research_packet` or `gather_more_evidence`), confidence, source-grounded evidence, source analysis, question decomposition, an autonomous phase trace, tool/generated-code observations, a hypothesis ledger, per-hypothesis critique ledger, independent ranking, experiment concepts, evidence gaps, next steps, and source references. Generation provenance reports the provider, selected model, model-call count, fallback-call count, and completed research-phase count. Its `status` is `review_ready` only when at least one extracted local document or observed public source is present; otherwise it is `needs_evidence` and preserves diagnostics without presenting the packet as review-ready.

The workflow has four logical steps executed through the same Docker-worker contract as VC Assistant: deterministic context preparation, one isolated autonomous Docker worker, and deterministic verification/publication. The autonomous worker may set or refine goals, create prompts, request allowlisted `mn-skills` tools, and execute validated generated Python. All such actions must appear in the autonomous session ledger. The final deterministic step rejects untraceable claims or missing review boundaries.

Each hypothesis must identify its mechanism, predicted observation, evidence support, counterarguments, and what would disconfirm it. Novelty and causal claims are always bounded assessments, never guarantees. The generated brief is a draft, not a paper or validated scientific result.

## Research Boundaries

Public queries contain only sanitized research-goal, domain, and question text.
`web_browser_skill` standard mode owns lightweight and rendered retrieval.
Login walls, robots restrictions, CAPTCHAs, rate limits, conflicts, and
unavailable sources are retained as warnings. The workflow never bypasses
access controls, contacts participants, collects restricted data, changes live
systems, executes an experiment, or submits a manuscript.

For medical, biological, safety-critical, or regulated topics, users must supply the applicable human oversight, ethics, institutional, and domain-expert review. The workflow is not clinical advice and must not be used to make treatment, diagnostic, or safety decisions.

## Persistent job data

Persistent knowledge, Milvus Lite data, and durable state belong to the stable
`job_id`. They survive run completion and cancellation; only explicit data
reset or confirmed job deletion clears them.

## Evaluation

- Source records preserve origin, retrieval time, access status, and warnings; run metadata is provenance, not evidence.
- Facts, inferences, hypotheses, and unknowns remain distinct.
- Candidate hypotheses are falsifiable and include a counterargument or disconfirming observation.
- The phase trace contains source analysis, question decomposition, competing-hypothesis generation, per-hypothesis adversarial review, probe planning, revision, experiment design, and meta-review.
- A normal run is publishable only when every required model call is live-backed and the fallback-call count is zero.
- Experiment and benchmark concepts name controls, measurements, decision rules, and approval dependencies.
- Missing, stale, blocked, and conflicting evidence is explicit.
- Fake/offline runs are deterministic and write the full output bundle.
- Consequential actions remain blocked pending human review.

## Persistent Job response service

The top-level Job response service exposes bounded role, schedule, safe
configuration, lifecycle, and latest-run context without an active workflow.
It cannot launch tools, execute experiments, configure, or start the job.

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
