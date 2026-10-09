# Architecture Advisor 3.7 validation — 2026-10-08

## Decision-first reports and coding handoffs

- Advisor/manifest regression suite: **125 passed, 34 skipped**. The skips retain
  the Linux RGX/runtime requirements. Final affected checks were rerun after
  updating the handoff text and finding prompt contract: **44 passed, 2 skipped**.
- Catalog review plus source/binary SDK package preparation: **22 passed**.
- Four additional workspace tests verify exact source/scope/counterevidence in
  coding prompts, no implementation handoff for unresolved work, bounded whole
  evidence omission, static-cycle investigation without fabricated remediation,
  identical prompt content in main reports/work packages/retained data and replay.
- Chromium checked exact clipboard content, selectable manual-copy recovery,
  prompt-type filtering, individual/all-prompt Markdown downloads and briefing
  export. All checks passed, with no JavaScript errors. All nine report views and
  640–1440 pixel resizing also passed.
- The real-source validation export now includes **75 Python files, 161 dependency
  pairs, one cyclic group and 200 commits**. Its cycle and evidence-gap prompts
  request investigation. It has no synthetic architectural diagnoses or proposed
  implementation packages; live model assessment remains not analyzed.
- The broad catalog run returned **720 passed, 71 failed, 37 skipped**. Remaining
  failures include existing missing fixtures, unrelated contract assertions and
  the pre-existing Local Spark deployment-address guard. Full log:
  `/private/tmp/architecture-advisor-catalog-tests-37.log`.

Prompt text has one blueprint-owned representation shared by JSON, Markdown and
the dashboard. The report leads with a proposed benefit and a bounded next action;
copy/export does not execute a coding tool. Finding annotations now appear in the
claim output shape consumed by the validator and report, rather than the separate
observation shape. Model instructions request a concrete user/engineering scenario,
the smallest improvement, a keep-as-is alternative and observable acceptance.

This update adds no production dependencies and changes no installed runtime or
desktop source. No live model job, production deployment or Linux RGX gate was
performed; the installed CLI/SDK mismatch described below still limits live
verification. Service-wide outcome tracking and actual runtime/check import remain
future integrations, not verified capabilities.

## 3.6 cumulative output checks

## Cumulative output and dashboard checks

- Advisor and manifest regression checks: **121 passed, 34 skipped**. The skips
  require Linux RGX or its related execution paths. After the final history-schema
  change, the affected manifest, publication and output checks passed again:
  **40 passed, 2 skipped**.
- Source and binary SDK package preparation for this advisor: **4 passed**.
  The manifest compiles with the required Job storage resource and static HTML UI.
- Twelve workspace tests verify frozen source/hash checks, exact co-change sets
  and denominators, cumulative snapshots, Job isolation, replay/tamper rejection,
  retained baseline citations, review attribution/invalidation, required web
  failure behavior, safe HTML embedding and SDK delivery at the Job folder root.
- An actual static analysis of the advisor's current Python payload captured
  **74 files, 155 dependency pairs, one cyclic group and 200 Git commits**.
  Multiple source revisions were retained in one isolated validation Job. No
  synthetic architecture findings, runtime measurements or check results were
  added. Live model assessment was explicitly marked not analyzed.
- Headless Chromium checked all nine views, source inspection, dependency-group
  filtering, exact co-change drill-through, saved views and resize transitions at
  widths **1440, 800, 640 and 1200**. No page overflow or JavaScript errors occurred.
  A separate, clearly labeled browser regression fixture verified required
  reviewer/rationale inputs, reviewer disagreement, JSON export and draft
  persistence. The fixture is not included in the real-source dashboard.
- JavaScript syntax and Git whitespace checks passed. Python modules are exercised
  by the focused suite; no new third-party production dependencies were added.

The real-source validation export uses the requested root layout at
`/private/tmp/architecture-advisor-real-output/delivery/software_architecture_advisor/`:
`data/` contains retained JSON and Markdown snapshots, and `web/index.html` is
the latest offline dashboard. These are temporary validation artifacts, not a
deployed customer assessment.

Reproduction from the blueprint checkout on this workstation:

```bash
PYTHONPATH=/private/tmp/architecture-advisor-test-deps:/Users/homer/Projects/mirror-neuron-set/Membrane/mn-context-engine-python-sdk/src:/Users/homer/.local/share/mn_venv/lib/python3.11/site-packages /Users/homer/Projects/mirror-neuron-set/mn-api/.venv/bin/python -m pytest tests/test_manifest_contracts.py tests/test_software_architecture_advisor.py tests/software_architecture_advisor -q --tb=short
```

The temporary dependency directory contains declared parser, document/image and
SDK local-source test dependencies. The test suite consumes sibling SDK, skill
and agent sources; nothing was installed into the shared runtime environment.

## Unfinished gates and specification scope

The broader catalog run returned **697 passed, 88 failed, 37 skipped**. Its failures
include absent GTM/Legal fixtures, unrelated blueprint assertions and unavailable
dependencies. The advisor's package-source preparation initially required the
SDK's declared `setuptools-scm` extra; the focused preparation checks passed after
installing it in the isolated test directory. The deployment-address guard also
rejects this advisor's pre-existing Local Spark endpoint in execution/policy/model
files, unchanged by this update. This is not a clean repository-wide gate. Full
log: `/private/tmp/architecture-advisor-catalog-tests.log`.

The installed `mn blueprint validate` command cannot start because its installed
CLI references the missing SDK module `mn_sdk.shared_run_store`; schema reading,
compilation and preparation were instead verified through the checked-out SDK
tests. No live Core/OpenShell model job, Linux RGX gate, image rebuild, release,
runtime reset or production installation was performed for 3.6. The 2026-09-28
provider restriction below is historical evidence, not a current provider test.

The output is a source-grounded implementation of the core investigation and
cumulative-delivery workflow. The entire supplied flagship specification is not
implemented: multi-repository/PR bundles, semantic contract compatibility,
authoritative runtime/check imports, approved rule/exception evaluation,
deployment/data/workflow reconstruction, performance/capacity modeling and web
natural-language answers need further typed evidence collectors or integrations.
The current dashboard discloses these gaps and does not promote proposed checks
or static reachability into verified behavior. It publishes at finalization;
progressive live investigation updates are not provided by the static page.

## Historical 3.0 validation — 2026-09-28

### Checks at that time

- Advisor regression suite: **59 passed, 34 skipped**. Skipped cases require the Linux RGX runtime.
- Ten new catalog tests cover hundreds of tasks through actual SDK handlers, phase barriers, dynamic follow-ups, independent challenges, replay, interrupted attempts, budget exhaustion, exact Unicode source citations, tamper rejection, all 150 aspects/23 sections, and proposed work-package traceability. Model responses in these tests are controlled fixtures.
- CLI workflow validator: **7 passed**, including child-template bindings and invalid-parent rejection.
- OpenCode skill: **9 tests and 12 subtests passed**, including sanitized provider-denial errors without fallback.
- Blueprint validation passed. New catalog modules pass Ruff undefined/unused-code checks; affected Git diffs pass whitespace checks.
- Full blueprint catalog suite: **411 passed, 50 failed, 37 skipped**. Failures were outside the advisor suite, including missing GTM/Legal fixtures and other blueprint assertions. This is not a clean repository-wide gate. Local log: `/private/tmp/architecture-catalog-full-tests.log`.

Focused reproduction from the blueprint repository (using the installed local SDK environment):

```bash
PYTHONPATH=/private/tmp/mn-opencode-validation /Users/homer/.mn/venv/bin/python -m pytest tests/test_software_architecture_advisor.py tests/software_architecture_advisor -q --tb=short -p no:cacheprovider
mn blueprint validate ./software_architecture_advisor
```

The temporary PYTHONPATH contains validation dependencies for this workstation; a prepared project environment should install the declared dependencies normally.

## Actual OpenCode/OpenShell use

The OpenCode skill ran OpenCode 1.18.33 inside OpenShell with the requested default `opencode/muse-spark-1.3-contributor-free` to generate the initial implementation. The coding invocation produced source files but ended with a failed-tool status. Generated code was subsequently reviewed and corrected, including SDK ownership, evidence propagation, citation validation, replay, publication and error handling.

A separate live check used a derivative of the locally prepared worker image, with OpenCode 1.18.33 and the required OpenShell runtime tools. The worker verified that PID 1 was `openshell-sandbox`. Real model requests reached OpenCode Zen but returned **HTTP 403** with the provider message: “OpenCode's free tier can only be used from within OpenCode.” The request was issued by the OpenCode CLI; the cause of the provider restriction has not been established. No paid or alternate model was used.

The live check reserved two actual calls, recorded their blocked results and published an explicitly partial report with all 150 aspect coverage entries and 23 section documents. These outputs demonstrate failure/budget handling, **not a successful architecture assessment**. Retained artifacts: `/private/tmp/architecture-review-validation-output`.

## Remaining verification

The final production Dockerfile has not been rebuilt through the complete platform preparation lifecycle, and the new catalog has not completed a deployed Core/Redis job with successful live model responses. The Linux-only regression cases were not rerun for this version. Provider access must work before a live assessment can complete. No packages were published or production cluster upgraded.

The bundled specification library is checked against its original manifest hashes. Static source review does not establish runtime performance, security, business impact or migration success. Such evidence gaps remain explicit verification tasks; generated work packages are proposals.

## Model configuration update

The setup guide now exposes the default Zen model and Local Spark Muse Glimmer 30B. Configuration tests cover both display labels and IDs, the local provider endpoint, and rejecting a model change within an initialized run. The local OpenCode model inventory confirms `spark/muse-glimmer-30b`; this update did not run a live architecture assessment against Local Spark. OpenCode 1.18.33 bundles the OpenAI-compatible SDK, so this provider does not require a runtime package-registry exception.
