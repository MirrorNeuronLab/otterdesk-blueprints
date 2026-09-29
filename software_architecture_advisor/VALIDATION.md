# Architecture Advisor 3.0 validation — 2026-09-28

## Current checks

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
