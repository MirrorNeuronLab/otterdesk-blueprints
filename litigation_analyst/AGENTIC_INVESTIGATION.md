> Historical autonomous-explorer design. Version 2.0 defaults to dynamic child workflows; see README.md. This implementation is retained for future model evaluation.

# Agentic investigation implementation

The workflow now prepares immutable original/normalized sources, builds and validates
persistent document and graph indexes, runs a manual-driven LLM investigation, and
renders a deterministic citation-checked review draft. The fixed-branch investigator
was removed. Hypotheses, revisions, alternatives, counter-evidence, errors and stop
reasons are retained in the agent checkpoint; SQLite stores exact evidence and the
final review projection.

Graph analysis, document reading and PDF extraction each publish an `mn.skills`
descriptor and a packaged SKILL.md. Deterministic Python callers and agent invocation
use the same APIs. Shared discovery, validation and checkpoint execution live in
mn-agents; no investigation-specific logic was added to the SDK. The document skill
now provides a persistent SQLite FTS5 lexical index, replacing the workflow's former
transient hashing index. Ranked search does not establish completeness.

## Verification

- 34 litigation/manifest tests passed; new litigation runtime coverage: 97%.
- 36 shared-agent tests passed, including source/wheel installation isolation.
- 33 focused skill/installation tests passed after the final atomic-index update.
- Shared invocation/checkpoint/index coverage measured 94% before that final update.
- Current-catalog regression: 295 passed, 35 skipped, 3 deselected.
- Full unfiltered repository run: 304 passed, 35 skipped, 54 failures, all in
  legacy VC/Financial Advisor tests and their parameterized runtime cases. Those
  blueprints live in the separate mn-blueprints repository and still import
  retired mn_blueprint_support. They were not changed by this task.
- Actual Linux RGX smoke passed in an offline disposable Docker container using
  synthetic emails, newly built wheels and a scripted model: graph ingestion/query,
  packaged manuals, retrieval, citation output, and completed checkpoint replay.
- Skill catalog synchronization, shared genericity audit, lint and diff checks pass.

The optional Docker regression is `tests/litigation_analyst/test_linux_worker.py`.
Set MN_LITIGATION_TEST_IMAGE to a cached Linux worker containing the prepared platform
Python dependency, and MN_LITIGATION_TEST_WHEELS to a local wheelhouse containing the
SDK, declared skills/agents and their platform-compatible prerequisites. The blueprint
must contain its prepared Linux engine. The test disables container networking and
uses no customer evidence. Ordinary tests do not require Docker or a live model.

## Runtime and release notes

The execution defaults are 24 skill invocations, 40 model decisions and 600 seconds.
The hard deadline requires the POSIX worker main thread. Cancellation is observed
between actions. Completed observations are reused; an interrupted in-flight read
may be retried. Snapshot/configuration/model/manual/descriptor changes reject resume.
Budget exhaustion and cancellation produce explicitly incomplete review drafts.

Existing pip/GAR declarations and source-mode resolution are retained. Source mode
ignores release pins; wheels carry their own manuals and descriptors. The declared
skill 1.3.24 and agent 1.3.10 releases must include these changes before GAR consumers
can install them. No packages were published and no live-model evaluation was run.
