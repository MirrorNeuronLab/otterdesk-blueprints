# Code verifier

## Activity-based run supervision

The workflow declares `execution.supervision: "activity"`. Matching Core and SDK
supervise process liveness and real packet/model progress without phase-wide
elapsed limits. Extraction and verification time allowances default to `null`;
operators may still set an explicit 1–3600 second computation budget. Individual
model requests remain bounded to 90 seconds; packet, retry, rule and turn limits
still apply. Human review retains its bounded approval expiry and advertises a
waiting state rather than stalled computation. Completion remains a durable
runtime receipt.

Version 3.1.0 changes only this blueprint and its offline code-search/static-analysis
skills. Use the updated skills and prepare a fresh Job/run with the existing runtime.
Existing reports and accepted-run checkpoints retain their original policy; a new
policy cannot resume an old investigation or reuse its approval.

Turn `SPEC.md`, `spec.md` and other Markdown/text documentation into a list of
software expectations. This co-worker saves editable `rules.md`, asks you to
approve the rules in Chat, investigates each approved rule separately, and writes a report with rule, pass/fail/unknown, evidence
references, and a confidence score from 0 to 1.

Choose a **local repository checkout or plain folder** containing the software
and its docs. A Git checkout is treated as files; uncommitted source is included.
Remote repository URLs are not fetched. Clone a repository yourself before
selecting it. No repository code, tests, hooks, installers or build scripts run.
The configured staging exclusions omit common dependency/build trees, including
`.venv`, `.git` and `node_modules`, before the platform copies inputs. This
requires the current SDK folder-exclusion support; reload the API after a local
SDK source update. Other folders remain subject to capture limits and exclusions.

## Run

Requires the existing MirrorNeuron runtime, Python 3.12, the declared `mn-skills`
packages, a working SDK model route, and a runtime computer with at least 48 GiB
of GPU or unified accelerator memory. The complete workflow and its managed model
run on that reserved computer; a 24 GiB mini cannot host this co-worker. In a
mini/Spark setup, MirrorNeuron selects Spark before accepting work. Existing Jobs
retain their runtime owner: a Job previously prepared on mini must be recreated
on an eligible computer after updating this blueprint. Changing its settings does
not move it to Spark.
The default model is the runtime default;
the blueprint preserves the SDK-prepared model/provider/endpoint binding.
An operator-registered remote default uses the runtime's LLM proxy with the same
model and credentials. It does not require a local copy of that chat model.
There is no fake-model success path. The new literal-search API requires the
code-search skill release with `TextSearchIndex.rank`/`SyntaxIndex.from_analysis`
and static-analysis `source_hashes`, or current sibling source with
`MN_USE_LOCAL_SKILLS=1` in local mode. Publishing that skill release precedes
binary catalog distribution. The workflow uses existing runtime components;
normal checkout staging requires the SDK's `excluded_directories` option.
The host-runtime agent retains its published API. Worker lifecycle and replay
use SDK/common/blocks `>=1.3.61.dev25,<2`.

```bash
mn blueprint run ./code_verifier \
  --set inputs.payload.input_folder=/absolute/path/to/your/repository
```

In OtterDesk, hire **Code verifier**, choose the source code folder in the first
setup question (it has no default path), and
start the review. The runtime stages inputs and owns output delivery. Reports
are saved beneath `~/Downloads/code-verifier/run_<timestamp>/` by
default, with authoritative artifacts in the runtime-provided run directory.
The report writer stages declared artifacts in the SDK-provided output folder;
the runtime copies them to Downloads after completion. `latest.html` links to
the most recently delivered run. Open its `web/index.html` in a browser, or use
the completed run's web report in Chat to inspect it in the conversation workspace.
The page and its handle are declared worker exports, using the same publication
contract as Drug Discovery.

For a tiny synthetic input, select `code_verifier/examples/sample_inputs`
as the source folder. It contains a name guard, a plaintext-password counterexample,
and no cancellation implementation. AI judgments remain evidence dependent;
deterministic tests use an injected model, never live model/network access.

## Review before verification

After extraction, **Review rules** appears in the OtterDesk conversation as one
searchable list. Each rule has a short title. Select a title to read the complete
Markdown statement and source reference. Lists use pages of 50 titles; search
covers the entire list, including rules on other pages.

Choose **Edit Markdown** to change a rule's short title or statement, preview the
Markdown, and **Save rule**. Saving changes only that rule in this run and opens a
fresh review of the revised list. It never approves the rules. Unsaved edits block
approval until saved or discarded. The captured repository and original source
references stay unchanged; edited rules are labeled as supervisor-authored.

**Approve all** accepts the entire current saved list, including rules outside a
search, plus its explicit extraction gaps and investigation limits. **Reject**
stops the review. Verification makes no model calls until Core confirms approval
of that exact version. A new run or changed content requires new approval.
Unanswered reviews share a one-hour deadline by default
(`review.human_review_timeout_seconds`, 1–3600 seconds).

The Markdown review requires the matching OtterDesk rule-list UI. Core and the
existing SDK interaction transport are unchanged: a bounded request points to an
immutable, SHA-256-checked run artifact; explicit edit and approval responses use
Core's existing revision/idempotency contract. Run-local files are audit records,
not approval authority. Interrupted saves are recovered from their Core receipts.

## Edit and add rules

Use the co-worker's existing Knowledge controls to add Markdown files beneath
`knowledge/rules/` in its **Job-scoped knowledge**, for example `custom.md`.
The seed `knowledge/rules/custom.md` is empty. Do not put review rules into the
manual or other reference documents. Each rule uses a stable ID and an optional short title:

```markdown
## NO-PLAINTEXT-SECRETS — Protect stored secrets

The software must not persist API tokens or passwords in plaintext files.

## CANCEL-ACTIVE-WORK — Cancel active work

A supervisor must be able to cancel active work without losing completed results.
```

Keep one independently checkable statement per heading. IDs start with a letter
and contain up to 64 letters, digits, hyphens or underscores. IDs must be unique
across files. Titles use ` — ` after the ID and are at most 120 characters.
Headings without titles remain valid. Use level-three or deeper subheadings
inside a rule. No prose goes before the first rule. Examples are in
`examples/rules.md`; they are not installed as live obligations.

`review.rules_mode=augment` extracts docs and adds custom rules. To edit a
generated rule, copy its section from `rules.md` into `knowledge/rules/custom.md`
and retain its `GEN-...` ID: the custom version overrides that rule.
`review.rules_mode=replace` verifies only your Markdown rules. To remove rules
from a generated list, edit the exported `rules.md`, upload that complete list to
`knowledge/rules/`, and use replace. Start a new run after editing knowledge;
an active run retains its original capture. Chat edits apply to the current run;
copy the exported titled `rules.md` into Knowledge to reuse those edits.

## Inspect results

- `rules.md`: editable authoritative list for this run; copy into knowledge for reuse.
- `rules.json`: rules, their source origins and full extraction coverage.
- `extraction-plan.json`: selected rule documents, generated reports excluded
  from extraction, source identity and packet budget before model work.
- `reviews/rules-<sha256>.json`: complete titled Markdown review list.
- `reviews/original-rules.json`, `reviews/edit-*.json`: original list and explicit edit receipts.
- `rules-review-request.json`, `rules-review.json`: bounded review deadline,
  exact ruleset digest and Core request identities. Approval authority remains Core.
- `report.md`: requested table, exact references, reasoning and confidence.
- `final_artifact.json`: the full machine-readable report and every result.
- `capture.json`, `source/`, `static-analysis.json`, `verification/`: captured
  source, syntax coverage and per-rule investigation receipts for audit.

**Pass** means inspected implementation supports the rule within the stated
static scope. **Fail** means a cited implementation path contradicts it.
**Unknown** means more evidence or review is needed. Docs alone, missing search
hits, comments and test source cannot earn a pass/fail judgment. Scores are
uncalibrated AI assessments; static judgments are capped at 0.85. No passing
report guarantees correctness, safety or complete requirement coverage.

## Scope and limits

Uses `mirrorneuron-static-code-analysis-skill` for source-backed syntax facts and
`mirrorneuron-code-search-skill` for offline ranked/literal retrieval, symbol lookup,
bounded traces and exact source spans. The SDK handles model calls. No grepai service,
embedding model or sandbox coding tool is needed for workflow verification.
Job conversation uses the standard knowledge/RAG response service independently.
The workflow's required review uses the existing SDK human-interaction producer,
Core decision receipts and OtterDesk conversation interaction stream. MirrorNeuron
must support `mn.interaction.v1`; an unavailable service never bypasses approval.

Capture accepts UTF-8 source, Markdown, text, reStructuredText and common config
formats. PDF/Word/image documents need conversion before selection. Hidden files except allowlisted `.github/workflows/*.yml` and `*.yaml`,
secret-like names, symlinks, dependencies and build folders are excluded. The
complete exclusions are recorded. Do not assume filename exclusions detect all
secrets: choose only source authorized for the configured model route. Private
source and reports remain confidential and are not published. A configured
external model provider receives bounded evidence excerpts.

Capture is bounded to 2,000 files / 10 MB; files above 500 KB are reported as
omitted. Custom knowledge is at most 100 Markdown files / 500 KB. Excess total
capacity fails visibly. `review.documentation_scope=current_requirements` excludes
documents below `benchmark-results`, `benchmark_results`, `test-results`,
`test_results` and `playwright-report` directories from rule extraction. Their
captured text remains available as evidence. Excluded documents are listed in
the extraction plan, rules.json and final report. Choose **All captured docs**
(`review.documentation_scope=all_captured_docs`) to extract those too.
Extraction starts with complete-line packets targeting 4 KB / 50 lines; a single
line may use up to 12 KB. The selected scope is checked against
`review.max_extraction_packets` (default 512, configurable 1–2048) before model
work. Models select trusted source-line IDs; the code copies the exact evidence
text and references. Models do not transcribe source quotes. Invalid selections
receive focused corrections that retain the original rule statements.

Malformed JSON, incomplete output and persistent selection failures automatically
split into smaller complete-line packets, within the same packet budget and
deadline. Transient model failures receive bounded retries with backoff.
`review.max_extraction_attempts` defaults to 3 (configurable 1–3 per packet).
Successful children survive a sibling failure. Unresolved source sections become
explicit `extraction_gaps` in rules.json, Chat approval and both report formats;
other documents continue. Deadline exhaustion leaves the remaining sections as
gaps. Three consecutive unavailable document packets stop further model requests
for that phase. Missing requirements are never represented as verified rules.
If extraction succeeds but identifies no rules, Chat asks you to review that
outcome; an empty report explicitly establishes no conformance result. If no
rules survive and source sections remain unresolved, the run fails before
approval or verification. `extraction-status.json` explains that outcome;
`extraction/drafts/` retains bounded typed error codes and stages, without provider
messages or request content. Sections skipped after the outage limit are labeled
`not_attempted_after_model_failure`, separately from actual failed requests.
Drafts, splits and unresolved receipts remain under `extraction/`.

Validated candidates are cached under the SDK-owned Job data directory,
`cache/code-verifier/extraction/`. Reuse requires the same source snapshot,
document hash/span and extraction policy, plus fresh evidence validation. A new
run always needs new human approval. Invalid cache entries are recomputed;
cache write failure cannot stop the run. The cache holds at most 2,048 entries
of at most 1 MB each. Complete run artifacts remain the audit authority.

Verification selects evidence IDs from seeded or explicit source reads, with trusted code copying
the cited text. Invalid actions, references and model replies receive recovery
feedback within the turn budget; the model can adjust queries and source ranges.
Working observations are compacted to 24 KB while the full investigation history
is retained. Large file inventories use a bounded preview; searches still cover
every captured file. After bounded retries, a failed rule becomes **Unknown** and other
rules continue. Failures in earlier rules never suppress a later rule's model
investigation; each approved rule receives its own bounded attempts within the
configured rule and verification time limits.
Saved outage placeholders without an investigation are assessed when work resumes.

Defaults allow model investigation of 2,000 rules (`review.max_rules`, 1–2000),
eight model calls per rule, with no default phase-wide elapsed deadline. Every
candidate remains in the rule list and report; rules beyond the investigation
limit or deadline receive Unknown with a reason. Extraction allows 8,192 output
tokens per request, verification 3,500; requests have 90-second timeouts and
100 KB input limits. Invalid setup, capture/storage integrity failures and missing
human approval remain blocking. Capture is of staged inputs; safe in-folder
symlinks may already have been dereferenced by staging, while escaping links are
rejected.

Tests: `python -m pytest tests/test_code_verifier.py -q` from the catalog.

Model calls declare the extraction, source-repair and investigation response
schemas through the SDK. Exact source-handle admission and human approval still
apply after structural validation. With the runtime's explicit fake-model mode,
an empty extracted list establishes no conformance result; custom rules receive
Unknown judgments. Fake mode never proves source correctness.
Review documents use the SDK's immutable, host-readable artifact publication so
the supervisor can load them after replication from a container-owned run.
The SDK publication adapter registers verified result, rules and report downloads
in the runtime output inventory.

Version 3.0.1 wraps verification actions in a `decision` object so strict model
routes receive an object-root JSON schema, with explicit action and status types.
Earlier schemas used a root union that such routes reject before returning a
response. This fixes the blueprint request contract without changing the runtime
or relaxing evidence requirements. Existing reports keep their original results;
start a new review with the updated blueprint to reassess them.

## Shared web report

The offline report uses `mn-web-report-skill` (distribution
`mirrorneuron-web-report-skill`) for the Geist shell, shadcn/ui controls,
Actions menu, tabs and non-modal evidence panel. Domain views and evidence rules
remain in this blueprint. Open `web/index.html` from a completed output; no
Node server, CDN or model call is needed to read it. Saved copies include the
shared assets. Markdown and structured evidence remain the authoritative outputs.
An optional web rendering failure is recorded in `presentation-status.json` and
does not prevent publishing those authoritative outputs.

## Native block composition (3.0.0)

All five phases bind directly to their domain implementations through SDK
`domain_operation` blocks in `extensions/blocks.json`. Each implementation
consumes `BlockContext`; no legacy phase or context adapters remain. Capture
resolves the staged input folder from declared local-input configuration and commits its snapshot and source
files. Downstream phases consume the committed capture reference. Mutable rule
and review checkpoints stay editable; Core decisions alone grant approval.

SDK storage owns path containment and atomic writes. SDK `publish_bundle` owns
required JSON/Markdown publication, immutable receipts, optional HTML isolation
and replay verification. This blueprint retains rule extraction, source evidence
admission, exact approval checks and the specialized evidence panel on the shared
web report shell. Output selection follows the declared artifact contract and
uses SDK copying into `MN_JOB_OUTPUT_DIR`; Core owns host delivery. Cancellation
is checked between document attempts, rule turns and review iterations.

## Scoped static verification (3.1.0)

`review.documentation_scope=current_requirements` is the default. Historical
changelogs and evaluation reports are recorded separately. Section headings,
fence state and preceding context survive packet boundaries. Tutorial instructions
and bare code/configuration examples cannot become product obligations; governing
prose can establish a requirement scoped to the specific example/tool. Extracted
rules retain subject, scope, modality, conditions and kind. Only exact scoped
duplicates merge, retaining all origins; potential conflicts stay visible.
The existing human review includes exclusions, excluded candidates and scope flags.
A supervisor rewrite clears stale extracted qualifiers and requires fresh approval.

Retrieval uses offline BM25 keyword/path ranking with identifier splitting and
existing Tree-sitter definitions, imports and caller/callee candidates. One index
is reused for the capture. `source_hashes` verifies every analyzed file, including
unsupported/parser-gap files. The model receives a compact role-based project map,
ranked implementation candidates and bounded exact source reads rather than an
alphabetical list dominated by benchmark output. Source, configuration, tests,
examples, generated artifacts and documentation have distinct authority.

The default eight model calls reserve two calls for a structured judgment and an
independent critique. `review.max_turns_per_rule` accepts 3–12 total calls. Early
judgments may use fewer calls. The critic sees the approved rule and selected
source, not the draft verdict. Conclusive judgments need matched scope, checked
conditions, direct enforcement/contradiction evidence and agreement. A configuration
value alone cannot prove behavioral enforcement. Generated output cannot prove
product behavior. Syntax navigation is not compiler binding or runtime proof.
Repeated queries receive specific recovery guidance. Full audit history survives
working-context compaction; selected source spans and stable read handles remain
available. Reports retain useful evidence and next steps when a verdict is unknown.

`diagnostics` records model calls, seeded/source reads, searches, empty searches,
repeated queries and unknown reasons. Reasons distinguish budget exhaustion,
provider/response failures, parser/capture gaps, ambiguity, insufficient evidence,
runtime-only properties and reviewer disagreement. Extraction exclusions remain
separate from assessed-rule counts. No unknown-rate target encourages guessing.
The public report retains pass/fail/unknown, exact source references and static
confidence caps. Source execution, network tools, arbitrary commands, automatic
fixes, model-route changes and approval bypass remain unavailable.

Extraction and verification checkpoints bind prompt/implementation policy, source
identity and approved rules. Old-policy runs require a fresh run and human review;
historical delivered reports are never overwritten. Runtime, SDK and desktop
contracts and the five workflow phases remain unchanged.

For an authorized delivered run, `python code_verifier/benchmarks/compare_capture.py
/path/to/run --output-dir /tmp/code-verifier-comparison` audits all prior conclusive
results and 26 unknowns stratified by origin. It writes confidential comparison
JSON/Markdown outside that run, comparing source roles and ranked source reads.
It makes no model calls and does not label new pass/fail judgments or claim measured
LLM accuracy. Run the focused blueprint/quality tests and affected skill suites
before an opt-in live run; the revised rules still require the normal approval.

The offline navigation/hash APIs are published in both skills at `>=1.4.1.dev0,<2`.
Publish static-analysis first, then code-search, before raising these blueprint
minimums. Version 3.1.0 uses these published skill versions with the existing
runtime and unchanged SDK dependency declarations.

Capture has no separate source-folder port: it resolves the required folder from
the SDK-owned staged `inputs.payload.input_folder` configuration. A default empty
workflow run-input port must not shadow that staged selection. Empty configuration
still fails visibly; no host-path or alternate-source fallback is introduced.

In a development installation with local skill overrides enabled, validate the
published pair with `MN_USE_LOCAL_SKILLS=0 mn blueprint run ./code_verifier ...`.
This is a per-command selection of the existing published-skill path, not a
persistent runtime setting. An older locally staged skill can shadow the released
wheel; refreshing the Job alone does not update that local source checkout.
The 3.1.0 live replay was launched in published-skill mode on the existing owner.


## Stage-aware conversation

OtterDesk reads `payloads/prompts/conversation.json` as optional app-owned guidance. It combines this role and stage policy with the pending question, confirmed non-secret setup answers, recent dialogue, selected report and fresh Job state. Short follow-ups retain their topic; a correction does not silently change saved configuration.

Use Memory or explicitly ask to remember, edit or forget an explanation preference. This affects Chat wording only; working rules and evidence keep their existing domain controls. The optional `inputs.payload.supervisor_instructions` array is app-managed, never a required setup answer or a new workflow permission.

Use the selected run report and exact source/rule references. Documentation and absence of search hits cannot prove implementation correctness. Only Core approval of the exact rule revision authorizes verification. A conversational yes or saved preference cannot approve, edit or remove rules. Use Review rules and Job knowledge for requirements. Never execute repository code or claim conformance from missing evidence. Existing submitted runs retain their configuration, evidence and approvals. An idle prepared Job may refresh through the existing conditional API without rehiring, resetting memory or mutating an active run.
