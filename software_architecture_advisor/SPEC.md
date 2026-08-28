# Software Architecture Advisor specification

## Outcome

Given one local source folder or a GitHub URL materialized by the connected
intake service before execution, produce a read-only architecture assessment
and copy-ready improvement prompts. The primary artifact is
`mn.blueprint.software_architecture_advisor.v3`; it retains the v2 fields and
filenames while adding eight validated model-stage records, aggregate real
token usage, a metadata-only model trace, model-authored analytical narrative,
and explicit finding origins. It includes source provenance,
a normalized fact database, repository/symbol/state/trust/test/deployment
evidence, traceable findings, counter-evidence, priorities, and a prompt
pack. It never includes changed source files.

## Workflow

1. `resolve_software_source` validates the source and requires the local model
   to produce a repository-specific investigation plan.
2. `map_architecture_evidence` inventories safe source and metadata files,
   creates a dependency/symbol graph, normalizes architecture facts, and runs
   separate component and cross-cutting reconstruction passes.
3. `assess_architecture_improvements` reconstructs architecture, triangulates
   hypotheses, permits only fact-grounded new findings, then runs a separate
   adversarial pass over every candidate.
4. `author_implementation_prompts` creates one coding-agent prompt per
   priority with model-authored objectives, options, tests, rollback, and stop
   conditions inside deterministic safeguards.
5. `draft_architecture_report` uses the model to draft the analytical narrative
   while deterministic renderers retain ownership of facts, metrics, and tables.
6. `audit_architecture_advice` runs the eighth model pass over the complete
   package, followed by deterministic grounding, usage, coverage, and safety
   checks.
7. `publish_architecture_advice` writes artifacts only after audit approval.

## Air-gapped contract

The worker is air-gapped. It may read the staged source folder and invoke a
runtime-prepared local model through the selected node's model gateway, but it
cannot reach GitHub, package
indexes, telemetry endpoints, or arbitrary URLs. `github_repo_url` therefore
belongs to a platform-owned pre-staging adapter that runs before this job's
isolation boundary; the analysis worker never runs `git clone`.

## Evaluation

- Every finding cites valid architecture fact IDs and relevant source paths.
- Every finding declares `deterministic` or `llm_grounded` origin.
- HIGH/CRITICAL findings use at least two independent evidence types.
- Every finding records counter-evidence checks and at least two options.
- Findings label static-analysis uncertainty instead of asserting runtime facts.
- Every improvement prompt includes a goal, evidence, allowed scope,
  non-goals, migration sequence, tests, acceptance criteria, and rollback.
- Final artifacts explicitly state that source changes are out of scope.
- Normal runs complete all eight model stages with real provider responses,
  nonzero token usage, and zero fallbacks; otherwise they fail closed.
- Raw prompts, source excerpts, credentials, and full model responses never
  appear in durable traces. `llm_trace.jsonl` is metadata only.
- Source metadata records whether a repository was local or pre-staged.

## Non-goals

This blueprint does not alter code, execute code, install dependencies, run
tests, fetch a repository itself, deploy a service, remediate a security issue,
or certify architecture/security/compliance quality.
