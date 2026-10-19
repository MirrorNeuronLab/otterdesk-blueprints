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


## 2026-10-17 remote Nemotron on mini — live run in progress

Run architecture-mini-nemotron-20261017-final uses mini (mirror_neuron@10.0.4.27)
and the registered nvidia/nemotron-3.5-super-vl-120b-a12b provider at
http://10.0.4.32:8000/v1 through mini's managed LiteLLM gateway. Admission used
the any-GPU/16-GB remote-provider hardware profile, without a local chat model.

Capture froze 367 code files and structural analysis completed. Hybrid original
source retrieval indexed 21,526 cached embedding pieces. The plan contains 744
tasks with no omitted source packets. Checkpoint attempt 3 preserved source
capture, structure, the embedding cache and prior admissions. The original
planner's 300-second deadline was too short for a full 64-task admission batch;
source workflow now declares a bounded 3,600-second planner deadline for future
runs. This immutable live run retains its original deadline.

The first real OpenShell child (scan-0001, .formatter.exs) produced a Core-committed
review artifact. Its claim, observation and citations passed validation against
the frozen source, with measured usage of 10,002 input and 3,231 output tokens.
The ordinary adapter also produced a complete larger diagnostic response; one
citation-ID transcription error was correctly rejected. A separate diagnostic
source review passed with three claims and four observations. No citation
validation was relaxed.

Focused checks passed: 103 SDK registry/output-budget/gateway tests, 25 SDK
context/stream tests, three provider-default integration contracts, eight advisor
source/profile tests and 12 manifest/profile tests (the profile cases overlap).
Touched-file lint and diff checks passed. This is live inference and handoff
evidence, not final report completion: the remaining review tasks, final report,
dashboard publication and commercial usefulness assessment are still pending.

## Focused static analysis validation — October 18, 2026

Scope is this blueprint, its tests and the new `mn-skills/static_code_analysis_skill`.
Runtime, SDK and reusable agent source were not changed. The existing runtime
registry selected Nemotron 3.5 Super VL as its default; `opencode.model` remains
`mn/default`.

- Public xv6 revision `f780d7850765d74cbdcd1fff4b822d8829f7c9bd`: the blueprint's
  static artifact builder completed in 0.961 seconds on this machine. Captured
  70 code files (including four assembly files available as text), 433 named
  functions, 316 aggregate file dependency edges and 503 function-change events
  from an 80-commit first-parent window. This is an extraction benchmark, not
  end-to-end workflow timing or a runtime performance claim.
- Source parser coverage: 64 parsed files, two partial files and four unsupported
  assembly files. Partial files retain complete error-free definitions/includes;
  malformed definitions remain unknown. Historical partial-file pairs remain
  gaps, rather than invented additions/deletions. The history read used two Git
  processes and 288 unique blobs; source/history extraction used no model calls.
- Focused workflow test executes the 40 baseline analysis/challenge/synthesis
  tasks through real SDK immutable handoffs, checks phase barriers and the
  four-task admission bound, and publishes the dashboard, report and host copies.
  All 150 catalog coverage entries remain present; 135 are explicitly unselected.
- Advisor/contract suite: 145 passed, 34 skipped for unavailable native RGX or
  opt-in live tooling. Additional final focused/UI-contract checks passed.
  Skills suite: 480 passed, two skipped and three live tests deselected.
- Skill wheel/source distributions build, the wheel includes its manual, the
  generated 33-entry portable/guidance catalog is synchronized, and the 31-skill
  genericity audit passes. No package was published or installed into the runtime.
- Browser checks exercised component selection, five retained function events,
  empty filtering, keyboard graph controls, absence of script errors and a
  600-pixel viewport with no page-level horizontal overflow.
- A separate live interpretation smoke test sent public xv6 source/facts through
  the SDK-resolved remote default gateway and received a JSON answer in 29.51
  seconds (10,818 input / 940 output tokens). Thinking was disabled for that
  bounded test request only. This confirms gateway/response operation, not
  factual accuracy or a complete OpenShell workflow run. The model's aggregate
  count attribution error prompted an explicit metric-unit rule in review prompts.

The complete new workflow has not been deployed or run through OpenShell on both
nodes. A new skill distribution must be available through the normal dependency
preparation path before a packaged deployment can consume it. Local wheel build
and deterministic tests do not establish that a new package is present in GAR.

The complete catalog gate also ran: 972 passed, 37 skipped and seven failures.
Four failures were CCTV loopback socket binds denied by the filesystem/network
sandbox; the remaining checks concern Litigation Analyst's newer dependency
minimums, Membrane SDK minimums and VC Assistant's structured-output environment.
These are outside this blueprint/skill change and were not modified.
The new map retention test additionally verifies that replaying an older run
cannot overwrite the latest map, while each archived snapshot keeps its own map.

The loopback subset passed with localhost access (five passed). Three unrelated
non-socket catalog assertions remain failing; the advisor suite remains green.


## Dynamic architecture views and growth review (2026-10-18)

Reviewed completed Job `job_saa-b9462300`, physical run `divdbySrK1Fjiw`, without
modifying its frozen inputs or results. The original model review was partial:
1/15 selected analyses, no supporting challenges, one-hour deadline exhausted.
Three model timeouts, six provider error events, two malformed blocked responses
and three undispatched analyses were retained. The two response failures lacked
`reason`, a field missing from the old example response shape; the prompt now
requires it. No new full live model assessment was claimed.

A regenerated copy is under
`/private/tmp/architecture-advisor-preview`.
Its HTML contains shells and local asset references; JSON and Markdown have
separate `data/` and `reports/` roots, including retained snapshot artifacts.
Original authoritative run and Downloads outputs remain unchanged.

The new deterministic xv6 history pass reconstructed 81 graph states in 2.366 s
using three batched Git processes, 290,255 bounded fact occurrences and 24.95 MB
of deduplicated frame/evidence JSON. At the same immutable revision
`f780d7850765d74cbdcd1fff4b822d8829f7c9bd`, supported files grew 65→66,
extracted named functions 416→433, call candidate pairs 885→915 and physical
supported source lines 11,844→12,380. The window now includes all first-parent
commits, merges and unchanged files, so it differs from the earlier path-filtered
non-merge event sample. Parser gaps and broad commit exclusions remain explicit.

- Skills suite: **483 passed, 5 skipped**, 24 subtests. Static package: **15 passed**.
  Fixtures cover unchanged caller re-binding, deleted paths/exclusions, first-parent
  merges, immutable dirty-worktree reads, parser gaps and explicit bounds.
- Advisor, manifest and publication/guard checks: **153 passed, 34 skipped** before
  the additional history-budget preservation test. The subsequent affected subset
  includes that new test. Tests verify prompt reason, bounded provider-failure stop,
  six-topic challenge waves, output separation, exact witnesses, replay and
  comparable/incomparable growth snapshots.
- Portable skill generator and genericity audit pass (31 shared packages plus
  two guidance skills). The D3 7.9.0 upstream bundle retains its ISC license and
  pinned SHA-256. The network-address guard verifies that exact hash instead of
  interpreting D3’s `.local` JavaScript property accesses as private DNS names.
- In-app browser checks exercised all five D3 views, exact relationship witnesses,
  co-change denominators/commit drill-through, commit baseline comparisons,
  persisted historical selection, graph zoom and 600-pixel resizing without page
  overflow. No unexpected JavaScript errors were observed. The manual JSON picker
  loaded all three data files on an HTTP fixture. The test browser blocked opening
  a new `file://` URL; native file-URL execution is not claimed as verified.
- Broad repository run: 973 passed, 37 skipped, 18 failures. Four report migration /
  vendored-guard regressions were then fixed and covered by the passing focused
  suite. A runtime snapshot verification failed while blueprint files were being
  edited; recheck with sources held stable. Remaining failures concern unrelated
  Litigation changes, Membrane/VC expectations, and CCTV socket permissions. No
  unrelated implementation or runtime was changed to make those tests pass.


Final targeted follow-ups: the new budget-preservation/publication subset passed
33 tests. The shared workflow runtime contract passed separately with sources
held stable (1 test, 12.29 s); no runtime changes were made. A focused review can
now reach `review_draft` when all selected topics and challenges complete;
intentionally unselected catalog topics do not force a partial status. Section
Markdown lists only selected topics; the complete 150-row audit stays in JSON.

The final budget/scope-status/publication follow-up passed **34 tests**.

Final complete advisor/manifest/publication guard rerun: **155 passed, 34 skipped**
(59.20 s). Final stable shared-runtime contract: **1 passed** (10.41 s).
The source scopes passed `git diff --check`; the portable catalog remains current
for 33 skills. The final preview has 20,558 bytes of HTML shells and no embedded
JSON script payloads. Native JSON loading and D3 playback/pause/scrubbing were
verified on the final localhost preview.

## Industrial minimal result page and graph playback (2026-10-18)

The result now opens as one five-tab page. Index and code-map entrypoints share
one renderer; all retained HTML shells refresh together with shared assets,
while their authoritative JSON/Markdown remain immutable. Archived links were
checked against six real preview pages with no broken local asset/report links.

- Advisor/manifest/publication/address guards: **155 passed, 34 skipped** (63.32 s).
- Actual xv6 browser checks covered the opening inspection action, shared focus
  across matrix/graph/hotspots/impact, evidence-backed call paths (32 functions,
  33 immutable source links for the selected example), and review prompt disclosure.
- Function graph comparison showed additions/removals in both entities and call
  pairs. Playback advanced from state 2 to state 12; all 160 shared displayed
  node positions stayed identical across a manually selected state change.
- The active preview was checked at 600 pixels and after restoring normal size;
  no page overflow. Graph scrolling and zoom remain internal. No browser errors
  or warnings were captured in the dedicated check tab. JavaScript syntax and
  scoped whitespace checks pass.
- The original partial model review remains 1/15 analyzed and 0 challenged.
  No new model assessment, data-flow slice, community discovery, architecture
  conformance verdict or runtime profile is claimed by this presentation update.
  Joern, CodeCharta and dependency-cruiser references informed the documented
  follow-on priorities. Runtime and desktop app sources were not changed.

The final retained-shell migration and replay subset passed **26 tests** (4.46 s).
A separate no-history browser fixture showed the supplied reason, no graph
history and disabled playback. The source-only Structure view remains available.

## Action-first overview, language expansion and score (4.2.0)

The first tab now foregrounds the proposed change, evidence status, reported
findings, candidate structural weaknesses and Plan/Investigate/Verify prompts.
The saved xv6 result still contains no supported defect findings and only 1/15
model topics analyzed; it is not presented as a clean bill of health. Prompt
bodies reuse the canonical report strings with separate IDs for each view.

The own-model score is `advisor-structural-v1`, maximum 100. For this frozen xv6
extraction the assessed points are 20.76/25 modularity proxy, 19.18/25 dependency
health and 18.18/20 change isolation: 58.12 points from 70 assessed. Ownership
and approved-rule conformance are unassessed (30 points), so the displayed range
is 58.12–88.12/100, not a final grade. The source parse coverage is 91.4%.
The score is new derived evidence over the frozen preview; it does not replace
its original source capture, model review or report claims.

- Advisor/manifest/publication/network guards: **163 passed, 34 skipped** (59.88 s).
- Shared skills, default non-live gate: **500 passed, 2 skipped, 3 deselected**,
  24 subtests (39.51 s). The warnings are existing crowdkit/pandas deprecations.
- Language package: 32 tests before the added alias-cache regression. Real pinned
  grammars cover C/C++, Python, JS/TS/Node variants, Rust, Go, Java, C#, Ruby, PHP,
  Kotlin and Swift. Tests verify spans, receiver identity, ambiguity, local import
  witnesses, Rust history frames and absence of invented cross-file call bindings.
- Portable generator validates 33 skills; genericity audit validates 31 packages.
  The bundled Codex quick validator rejects the generator-owned `compatibility`
  frontmatter field; the repository’s current standard-format generator/check
  passes. Generated files were not hand-edited to satisfy the older checker.
- Qodo comparison is based on its published Software Map and enterprise pages,
  not an independent accuracy benchmark. Compiler/type binding, multi-repo/PR
  updates, approved rules and reliably completed model findings remain gaps.

No runtime, SDK, reusable-agent or desktop source changes were made. The model
alias remains `mn/default`, preserving the user's runtime override. No new live
model assessment or repository execution was performed.

Final follow-ups: **33 language-package tests passed**, including one parse per
shared blob/grammar across Node extension aliases; portable/genericity checks
passed. The shared workflow runtime contract passed **1 test** (11.71 s) with
sources held stable. Its implementation was not changed.

The final affected static-publication/score subset passed **17 tests** (2.31 s).
The final Overview has unique DOM IDs and no page overflow at 600 pixels or
after restoring the regular viewport. Its canonical planning prompt matched the
saved report text byte for byte; all five score dimensions and missing evidence
were checked in the browser. No new model review was performed.

## Cross-repository review and RedisRaft (4.2.1, 2026-10-19)

Validated the public `RedisLabs/redisraft` repository at immutable revision
`ade4aa8e6aa5c3b21678a1998309825f06567d4f`, using real source capture, pinned
Tree-sitter grammars, Git objects, graph layers, publication and browser rendering.
The analyzed checkout remained clean. Repository source, builds and tests were
not executed. The xv6 default and existing `mn/default` selection are unchanged.

The result contains 76 captured files, 909 named functions, 152 file dependency
pairs by kind and 81 committed graph states. Coverage is 54 parsed files,
4 partial files and 18 text-only files; 7,420 call sites remain unresolved.
The current `syntax-3` re-extraction took 0.240 seconds; history took 4.865
seconds with three Git processes and 281 unique blob/grammar parses. Text-only
sources retain 927 measured physical lines instead of a fabricated zero size.
These are local observations, not performance guarantees.

The first static-only runtime test dispatched 19 unassessed review tasks and
finished in 383 seconds including setup. The corrected blueprint dispatches
none and completed the next full static-only run in 60 seconds including setup.
Cache warmth differs; this is not an isolated speed benchmark. The task audit
retains all 19 unassessed tasks, zero model attempts, partial review status and
an explicit static-only stop reason. No runtime change was required.

The initial bounded four-call model test exposed an ordering defect: graph scope
was chosen before static function witnesses were available. This returned
`entity_unresolved` while the real repository graph was present. Retrieval now
binds source-backed application candidates before graph planning and prefers
distinct source files. Test-specific questions still favor tests. A subsequent
real request correctly seeded seven application files, including `src/raft.c`
and `src/serialization.c`. Focused review starts with a measured cycle when one
exists, then challenges completed analyses before further work.

The corrected two-call live test used the existing runtime default, 180-second
call bounds and a 600-second review allowance. Both responses failed structured
source-evidence validation; one cited an ID absent from the frozen request.
The report correctly retained two blocked tasks, zero accepted findings and
partial model coverage. There were no provider timeouts in this second test.
This validates retrieval and rejection behavior, not reliable LLM defect review.
No invalid citation was repaired, substituted or accepted, and no model route
or runtime configuration was changed.

The Overview now favors measured investigation over unchallenged proposals,
shows actual parse/call-target coverage and text-only formats, and surfaces the
three largest adjacent topology transitions. Replay selects the changed entity,
relevant file/function level and previous graph state. For the log-compaction
example, the browser showed +95/-72 call pairs and +35/-11 functions. Parser-gap
paths are excluded from those change counts. Incomplete structural scoring shows
`Evidence incomplete`; the possible interval and 80 unassessed points remain
available in the score disclosure.

- Advisor/manifest/publication/network guards: **176 passed, 34 skipped** (61.52 s).
- Shared skills non-live suite: **504 passed, 2 skipped, 3 deselected**, 24 subtests
  (41.79 s); four existing crowdkit/pandas warnings.
- Static package: **36 passed** (2.05 s), including real 13-language grammars,
  legacy non-UTF-8 history and case-insensitive history exclusions.
- Shared workflow contract: **1 passed** (11.92 s); runtime implementation unchanged.
- Portable skill catalog: 33 skills current; genericity audit: 31 packages passed.
- Browser: correct transition, entity, level and baseline; no duplicate DOM IDs,
  no overflow at 600 pixels, and no console errors/warnings. JS syntax and scoped
  whitespace checks pass.

Portability checks cover mixed Rust/Node modules, C and Python graphs, unknown
source formats, explicit custom suffixes, Unicode/space-containing paths,
non-Git repositories, missing history, unparsed graphs and missing score evidence.
Capture supports an explicit source suffix catalog and configurable extra suffixes;
unsupported languages stay text-only. This does not establish complete semantic
analysis for every language, framework, build system or repository size.

The final fresh runtime publication uses `syntax-3`, retains 927 physical lines
for text-only inputs, dispatches no review children and consumes zero model
attempts. It finished in 151 seconds including the changed skill/image preparation
and source staging; the earlier warm static-only run took 60 seconds. The final
static result and the separate blocked live-model review are both retained.

The final presentation follow-up passed **4 standalone browser-policy tests**
(0.33 s). The real RedisRaft treemap now labels text-only Terraform/shell files
as `history unknown`, with neutral grey fill. Directory subsets and historical
function parser gaps produce lower-bound counts rather than false exact zero
churn. Browser verification confirmed those titles, no overflow and no console
errors. Only derived HTML/JS assets were refreshed; frozen JSON/Markdown remain
unchanged.

## Focused file/function interface — 2026-10-19

The result page now has eleven single-purpose tabs in a restrained side navigation.
Graph, matrix, call paths, impact, evolution, co-change and size/churn each have
one dedicated view. Overview contains the lead investigation/change, findings,
compact coverage and at most two prompt previews. Prompts, score and evidence
coverage have separate tabs. Selected-entity evidence, exact records and reading
notes are expandable below the chart; a repeated blast-radius inspector is gone.
Directory selection, directory matrix ordering and directory treemap grouping
are removed. The flat treemap retains the distinction between unknown history
and measured zero churn. Saved scoring formulas and frozen source/review data
are unchanged. Content-derived script/style URLs prevent a refreshed HTML shell
from loading an incompatible cached asset.

Validation:

- **178 passed, 34 skipped** in the affected advisor, publication, manifest and
  network-address suite (57.44 s). The focused presentation/static/publication
  subset passed **35 tests** (6.32 s), including stale-asset cache invalidation.
- All eleven RedisRaft tabs rendered one active panel at normal width and 600 px,
  with zero page overflow. Chart tabs rendered one chart. Restored sizing also
  retained the layout. xv6 loaded the same eleven-tab page successfully.
- Matrix cells revealed source witnesses by pointer and keyboard; replay selected
  the prior-state comparison and function-level LogFree change (+95/−72 call
  pairs, +35/−11 functions). Keyboard scrubbing and play/pause worked.
- File/function selection retained the corresponding source path. An unmatched
  search produced a clear empty state, a disabled selection and no phantom node.
  Prompt copying reported success. No duplicate IDs, directory options, browser
  console warnings or errors were observed.
- JavaScript syntax, Prettier and scoped diff whitespace checks passed. Only
  derived presentation in the local RedisRaft and xv6 exports was refreshed;
  no runtime, SDK, desktop or model configuration was changed.

## Large graphs and switchable layouts — 2026-10-19

The graph tab no longer uses fixed slots for 14 neighbors, and evolution no
longer truncates at 160 entities. Both use one Canvas scene with D3 zoom and
quadtree picking. Users can choose Organic (recommended default), Sequential,
or Radial, following the categories in the Cambridge Intelligence reference.
These are local implementations using the bundled D3 library, not the vendor's
SDK or an assertion of equivalent layout quality. Directory grouping remains absent.

Organic uses deterministic heavy-edge matching and coarse-to-fine force
refinement with D3's Barnes–Hut repulsion. Sequential condenses candidate cycles,
assigns dependency ranks and performs six barycenter sweeps. Radial positions
minimum undirected distance levels from the selection. Disconnected graphs are
packed separately. All retain original file/function identities and relationships;
spatial groups do not establish architectural modules or approved layers.

HTTP layouts use a cancellable worker with a 20-second deadline and a four-result
cache. The renderer bounds eligible displays at 10,000 entities and 50,000
relationships, explicitly reports omissions, and retains the selected entity.
The default connected scope hides isolates; All entities includes them, and
Selected + 2 hops narrows the scope. Zoom/pan, Fit graph, Focus selected, adaptive
labels and exact evidence tables support inspection. Temporal positions use the
same committed union within each layout/scope; time changes do not rerun layout.
Offline file mode uses the same algorithm on the main thread.

Validation receipts:

- Affected blueprint/publication/manifest/address suite: **185 passed, 34 skipped**
  (61.87 s). Seven standalone layout tests cover cycles, deep chains, deterministic
  coordinates, caps, unchanged inputs, worker errors, radial distances and stable
  temporal union. These tests exercise the actual bundled D3 implementation.
- RedisRaft: switching all three layouts retained **510/909 connected functions,
  838 call-candidate relationships** and the same selection. All-entity scope
  showed **909/909 functions**. File scope showed **51/76 connected files and 152
  relationships**. A Canvas pointer selection changed to blockedCommandsLoad and
  updated its source relationship counts. Graph replay retained the LogFree
  comparison (+95/−72 call pairs, +35/−11 functions).
- xv6: Organic showed **61/70 connected files and 316 relationships**. All three
  layouts rendered at an actual 600px viewport with zero page overflow; the
  viewport was restored. RedisRaft was separately checked at normal width.
- Synthetic stress fixture (explicitly labeled test data): **10,000 entities /
  40,000 relationships** across 100 connected graphs. Local Node layout times:
  Organic 1,625 ms, Sequential 13 ms, Radial 27 ms. A single connected cyclic
  10,000-node/40,000-edge graph took 2,202 ms with Organic; all coordinates were
  finite and all entities retained. Times are local observations, not universal
  performance guarantees.
- Browser stress fixture reached the layout-ready state in **1,508 ms**, with
  **90 animation frames** while arranging; one Canvas displayed all 10,000 nodes
  and 40,000 relationships. This timing covers layout readiness, not a calibrated
  end-to-end paint benchmark. No console warnings/errors or page overflow were
  observed. The temporary stress-test tab was closed.
- Source/asset syntax, formatting and whitespace checks passed. Frozen JSON and
  Markdown were preserved; only derived presentation assets were refreshed. No
  runtime, SDK, desktop, model selector or extraction skill changes were required.

## Comparison context, replay, and selection evidence — 2026-10-19

Implemented the six presentation improvements in order, refreshing and reviewing
the RedisRaft preview after each step. Growth since the window baseline remains
the default. A single pure `comparison-presentation.js` model supplies comparison
modes, safe changes, ranked summaries, inspector rows, prompt matching, framing,
and scope accounting. Cycle membership reuses the layout engine's iterative SCC
mechanics. Persisted analysis schemas and records are unchanged.

Validation receipts:

- Affected blueprint/publication/manifest/address suite: **192 passed, 34 skipped**
  (64.35 s). Seven focused presentation tests cover baseline modes and missing
  dates, same-state comparisons, definition-only edits, gap-safe removals and
  cycle changes, historical entities, ranking, scope/display accounting,
  canonical prompt matching, and the real renderer's framing/camera lifecycle.
- Browser checks verified window/previous/custom comparison labels, first-frame
  date unavailable, disabled change zoom for identical states, replay controls
  above the graph, and sticky playback while inspecting expanded evidence.
- RedisRaft retained **51 files / 152 relationships** and **510 functions / 838
  relationships** in all three current-snapshot layouts. Historical replay of
  log compaction retained `src/log.c::LogFree`, **95 added / 72 removed call
  pairs**, and **35 added / 11 removed functions**. All three replay layouts
  retained **472 functions / 821 comparison relationships** and the selection.
  The removed function's source and relationship witnesses link to the baseline
  revision `8327bec0b22734137150ab5bd43f5a23459af335`.
- xv6 evolution rendered **62 files / 342 comparison relationships** with all
  three layouts at an actual **600×900** viewport. RedisRaft was checked at
  **992×864** and **600×900**, including wide→narrow→wide resizing. No page
  overflow was observed. Compact replay and canvas fit the available viewport;
  an obsolete 230px CSS minimum was corrected during the resize review.
- Explicit selector and summary selections opened the inspector. Escape and
  Close dismissed it and restored focus. The narrow sheet occupied the bottom
  432px of a 900px viewport; the desktop drawer remained non-modal. Before/after
  source URLs were revision-bound. Clipboard contents exactly matched the saved
  prompt textarea. Equivalent evidence tables remained accessible. Other tabs'
  linked selection was checked through Call paths; all eleven tabs loaded
  without console warnings/errors.
- The existing synthetic fixture retained **10,000 functions / 40,000
  relationships** in Organic, Sequential, and Radial. A cold Organic load reached
  ready after **1,507 ms**, with **90 animation frames** during calculation; an
  interaction was handled while layout was running. This is a local readiness
  observation, not a general performance benchmark. The temporary tab was closed.
- Derived assets and retained graph HTML shells were refreshed together in xv6,
  RedisRaft final, and RedisRaft review exports. Byte hashes confirmed **63, 55,
  and 55** frozen data/report files respectively stayed unchanged during refresh.
  Syntax/formatting and scoped whitespace checks passed. No runtime, desktop,
  extraction, skill, or model configuration changes were made for this work.

## Calm report shell and progressive disclosure — 2026-10-19

The opening view now contains one measured investigation or supported planning
recommendation, one primary evidence action, a visible assessment/coverage cue,
and a compact saved-prompt row. The repeated cycle card and empty findings
message are gone. Additional findings/proposals use concise inspectable rows;
more than three observations expand on demand. Empty source evidence offers a
scope review without inventing a recommendation, and unavailable history does
not become zero churn.

The logo-free header shows the report title and source identity, with all global
header actions in a right-side Actions dropdown. Revision/capture metadata opens
in the evidence panel. Four common views remain visible; seven additional views
are under More views. Layout/scope/filter settings are in Options, zoom/framing
commands in Graph actions. Comparison identity and replay remain visible. Source
lists, detailed relationship records, scoring formulas, measurement tables, and
methodology expand when needed. The non-modal evidence panel is retained and
also supports recommendations, findings, proposals, prompts, and report details.

Validation:

- Affected blueprint/publication/manifest/address suite: **194 passed, 34 skipped**
  (63.29 s). The final focused presentation/publication run also passed **51
  tests**. New shell checks cover header action placement, primary/secondary
  navigation, unique identities, native form keys, menu keyboard navigation,
  outside-click dismissal, and menu-first Escape handling.
- RedisRaft overview reviewed at **992×864** and **600×900**. The recommendation
  and prompt fit on the narrow first screen with no horizontal overflow.
  Prompt text opens immediately, and clipboard text equals the canonical saved
  prompt. Escape restores focus; an open action menu closes before the panel.
  Actions remains usable above an open desktop evidence panel.
- Graph evolution retained **52 files / 159 comparison relationships** in Organic,
  Sequential, and Radial through Options. Graph actions, change zoom, previous/
  next replay, and resizing **992→600→992** worked without page overflow. The
  canvas and playback remained within the available viewport. All eleven tabs
  loaded without console warnings or errors, including keyboard End/Home into
  and out of More views.
- xv6 uses the same shell and recommendation/evidence pattern at 600px. Source
  references remain revision-bound and collapsed by default. A labeled synthetic
  rich-report fixture checked findings/proposals, escaped `<source>`/`&` text,
  hidden additional observations, and a long source identity with a full tooltip.
  A separate empty fixture offered scope review and no fabricated recommendation.
  Temporary fixture tabs were closed.
- Refreshed derived assets and retained HTML together for xv6, RedisRaft final,
  and RedisRaft review exports. Hash comparisons preserved **63, 55, and 55**
  frozen data/report files. Runtime, desktop, extraction, and model configuration
  were unchanged. The reusable shell pattern and adoption boundaries are
  documented in `REPORT_DESIGN.md`; other blueprints were not migrated.

## Geist report foundation (2026-10-19)

- Bundled Vercel's published report CSS unchanged, with SHA-256 provenance,
  and official `geist@1.8.1` Sans/Mono WOFF2 fonts with their SIL OFL license.
  The public npm registry did not expose `@vercel/geistcn`; the report uses
  Vercel's published static UI primitives instead. No community React clone,
  build prerequisite, external font request, runtime or model change was added.
- Adopted neutral Geist surfaces, typography, fields and primary controls while
  retaining the no-logo header, one Actions menu, progressive disclosure and
  non-modal evidence panel. Corrected foundation style conflicts in the compact
  header, graph controls and coverage disclosure.
- Affected blueprint/publication/manifest/address suite: **195 passed, 34
  skipped** (59.38 s). Added pinned-vendor/font integrity and offline dependency
  checks, plus publication checks for current and retained shells.
- RedisRaft and xv6 reviewed at **992×864** and **600×900**, with no horizontal
  overflow. All eleven RedisRaft views, all three layouts, replay, keyboard menu
  navigation, Escape/focus restoration and the mobile evidence sheet worked.
  Copied prompt text matched the canonical saved text (57,455 characters).
  xv6 source references remained bound to the captured revision. Browser
  diagnostics were clear.
- Synthetic empty and rich fixtures retained honest missing-data states,
  escaped finding text and a discoverable full long source identity. The
  existing **10,000-function / 40,000-relationship** fixture became ready in
  1,477 ms and handled interaction after arranging. Temporary tabs were closed.
- Refreshed all three exports and their retained HTML with local CSS/font
  dependencies. **173 frozen data/report files** remained byte-identical.
  The reusable integration contract and dependency update procedure are in
  `REPORT_DESIGN.md`; other blueprints remain unchanged.

## Actual shadcn/ui component migration (2026-10-19)

- Replaced the custom interaction shell with ten actual shadcn/ui + Radix
  components: Button, Dropdown Menu, Tooltip, Tabs, Collapsible, Popover, Sheet,
  Input, Native Select and Textarea. React and Lucide are bundled locally.
  Official registry sources, a locked build, complete license notices and
  source/output hash receipts are retained under `report_ui/` and `vendor/`.
- The evidence Sheet is non-modal, with a valid title/description and no overlay.
  Menus use Radix keyboard behavior. Graph commands use named UI bindings rather
  than querying closed portal content. Large select options remain domain-owned
  and memoized. Prompt text and exact evidence tables retain their data contract.
- Final blueprint/publication/manifest/address suite: **197 passed, 34 skipped**
  (66.66 s). Five actual-bundle component scenarios also passed: dropdown
  keyboard/focus, nested Escape with a non-modal Sheet, Tabs/Home/End disclosure,
  native select/prompt byte preservation, and graph command availability.
- RedisRaft reviewed at **992×864** and **600×900**, including all eleven views,
  three layouts, replay, filter focus, graph commands, menu-first Escape and
  source selection. No horizontal overflow. At the narrow replay size the
  graph ended at y=899. The 468px bottom Sheet remained non-modal. Canonical
  prompt copying matched the saved text.
- xv6's long proposed change wrapped at 600px without overflow; its evidence
  Sheet and browser diagnostics were clear. The **10,000-function / 40,000-edge**
  fixture arranged in **1,510 ms** and handled interaction. Its explicit test UI
  adapter was updated for the graph command contract, retaining its strict CSP.
- Current and retained shells were refreshed for all three exports. The same
  **173 saved data/report files** remain byte-identical. The runtime, desktop,
  extraction, model configuration and other blueprints were not changed by this
  migration. `REPORT_DESIGN.md` describes the reusable component composition.
# Overview score summary

Overview now shares the full score tab's headline presentation policy and shows
only the score/range or evidence status, assessed weight, and a Full score link.
Verified the RedisRaft incomplete-evidence state and xv6 provisional range,
keyboard navigation to the score tab, and the RedisRaft layout at 992×864 and
600×900 without horizontal overflow. All 173 frozen source/review artifacts
remained byte-identical after refreshing the three previews. Affected suite:
199 passed, 34 skipped. Screenshot:
`/private/tmp/architecture-advisor-validation/overview-score-summary.png`.

# Shared report skill migration

Common report components, Geist fonts/theme and offline template composition now
live in `mn-skills/web_report_skill` (`mirrorneuron-web-report-skill`, requested as
`mn-web-report-skill`). Architecture-specific graph controls and data policy stay
here. Litigation Analyst and Code Verifier consume the same skill through their
declared dependencies and Python rendering/publication APIs. No runtime or desktop
source changed. A wheel was built and rendered successfully from an isolated
extraction, without installing it into the runtime. GAR deployments require the
new package to be released through the normal skill release process.

Validation: 531 shared-skill repository tests passed (2 skipped, 3 deselected);
366 blueprint/catalog checks passed (36 skipped). Six existing Litigation Analyst
planner regressions remain in `test_dynamic_rounds.py` and
`test_planning_context.py`, against the already modified `round_planning.py`.
The migration's report/publication and Code Verifier checks pass. Both compiled
component suites passed their five scenarios, and eight Litigation navigation/
reading scenarios passed. Portable catalog and 32-skill genericity audits pass.

Browser review covered both domain reports at 992×864 and 600×900, wide/narrow
resizing, non-modal evidence, keyboard dismissal/focus return, rule filtering,
empty filtered results, captured source reading and retained legal report tabs.
Architecture Advisor's Organic/Sequential/Radial controls and replay toolbar
remain functional. The 173 frozen architecture source/review artifacts remain
byte-identical after refreshing derived previews and retained HTML shells.

The downloaded litigation copy was statically verified to retain exact script/
style CSP hashes, two local executable bundles, zero external assets, no active
evidence panel, and originals excluded. The in-app browser blocks `file:` URLs,
so opening that downloaded copy in the browser was not verified. HTTP previews
and the isolated-wheel renderer were verified. Preview data is deterministic
test data, not a new model analysis. Screenshots:
`/private/tmp/architecture-advisor-validation/shared-litigation-evidence.png` and
`/private/tmp/architecture-advisor-validation/shared-code-verifier-overview.png`.

