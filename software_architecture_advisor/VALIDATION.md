# Dynamic child-workflow validation

## Structural baseline update (2026-09-24)

Blueprint 2.2.0 adds `analyze_dependency_structure` between capture and investigation. The step reuses the existing frozen dependency layer and publishes a bounded DSM plus source-linked JSON measures. The planner sees only a compact summary; findings still require support and counter-evidence review. The analyzed repository is not executed.

The setup guide now exposes the goal, and publication emits a report-digest-bound review choice into the standard human-event ledger. The desktop conversation renders reusable approval, judgment and missing-information cards with structured options and records the selected direction. This post-report choice does not branch the active workflow.

On this macOS checkout, using the local MirrorNeuron virtual environment on `PYTHONPATH` with Python 3.11:

- `tests/test_manifest_contracts.py`: 5 passed.
- `tests/test_software_architecture_advisor.py` and `tests/software_architecture_advisor`: 49 passed, 34 skipped. The skipped cases require the Linux RGX binary.
- `git diff --check`: passed.
- Desktop app: production build, TypeScript typecheck, lint and architecture checks passed; four affected component/unit files passed (146 tests).
- MirrorNeuron API: human-ledger and canonical route suites passed (41 tests). Shared-run responses were verified against the mapped submission ledger.
- The desktop full suite is not green: 976 passed and 90 failed across four files. A reproduced failure in `worker-blueprints.test.js` stops at the existing setup launch gate before reaching its human-response assertion; the focused conversation tests above pass.
- Full `tests` catalog gate: 344 passed, 37 skipped, 44 failed, 55 errors. The errors include missing `pypdf`/`PyPDF2` for Litigation Analyst; remaining failures occur in other blueprints. The focused advisor tests pass. This is not a clean catalog gate.

This update does not add multi-repository snapshot selection, G0/G1 mid-run interactive gates, an executable G2 branch, or isolated target-code probes from the supplied DAG design. The blueprint remains a static/read-only investigation with proposed verification tasks; no probe outcome is represented as measured.

Validated on 2026-09-07 against the companion SDK/Core source and the published ARM64 Linux RGX binary in Docker. No analyzed repository code was executed.

- SDK compiler, child declaration, static/dynamic workflow and public progress suites: **81 passed**.
- Core child lifecycle, workflow ledger and existing dynamic workflow suites: **54 passed**. Includes round barriers, partial-execution recovery, stale/duplicate completion, cancellation, invalid plans, isolated state, parent completion and private progress projection.
- Complete Architecture Advisor regression suite in Linux: **70 passed, 45 graph-query subtests passed**. Covers source acquisition, frozen hashes, all graph families, lazy materialization, citations, budget reserve, deadline exhaustion, model-response replay and actual SDK worker handlers.
- Host advisor and manifest suites: **39 passed, 34 Linux-only tests skipped**; the Linux run covers these graph checks.
- Scripted SDK-handler smoke with real RGX: two different committed rounds, eight operations, one independent review, durable replay without new model calls.
- Configured live model through the local gateway on the synthetic payment fixture: **three rounds, 45 graph/search operations, 18 model calls, three independent reviews**. The report is explicitly partial at the round limit. All final findings are inconclusive and their roadmap entries require verification before implementation. The original project-specific model proposals are retained as deferred advice and in JSON.
- The final live report was regenerated from its recorded responses with new model calls explicitly forbidden, revalidating citations and source hashes.
- Touched Core files pass format checks; new Python modules pass lint; affected diffs pass whitespace checks.

The live smoke uses deterministic hash retrieval to isolate graph/planning/review behavior from embedding-provider availability. It does not validate the default neural embedding service. Production Core/Redis orchestration is covered by deterministic ledger tests here, not a deployed cluster run.

## Remaining shared-environment gates

The last full catalog run reported 289 passed, 37 skipped and 70 failures. A stale advisor graph-package assertion was subsequently corrected and its binary preparation check passes. Remaining failures include missing local SDK source-version metadata (also affecting advisor source staging), retired `mn_blueprint_support` imports in other blueprints, and unrelated service/contract checks. Full catalog output is retained with the validation artifact. These failures are not presented as a clean catalog gate.

Core `mix compile --warnings-as-errors` remains blocked by existing redundant-clause type warnings in `persistence/redis_store.ex` and `runtime/runtime.ex`; the affected lifecycle tests compile and pass.

Deploy the matching SDK compiler and Core child-workflow implementation together before submitting blueprint v2. No packages were published and no running cluster was upgraded.

Live report and its supporting artifacts: `/Users/homer/Projects/mirror-neuron-set/artifacts/architecture-advisor-live-review/report.md`.
