# Code verifier specification

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

## Mission and outputs

Execution requires one accelerator with at least 49,152 MiB (48 GiB) of GPU or
unified accelerator memory, enforced as a hard placement requirement. All phases
and managed inference share the selected computer's run reservation. A smaller
computer may submit and stage inputs but cannot own the workflow. In a mini/Spark
topology, the 24 GiB mini is ineligible and Spark owns the Job. A missing eligible
computer blocks preparation; it never selects mini or routes managed inference
outside the reservation. Saved Job definitions retain their owner and requirements;
existing Jobs on an ineligible computer must be recreated on an eligible owner.

Given a local repository checkout or plain software folder, read complete captured
`SPEC.md`/`spec.md`, Markdown, reStructuredText and text documentation; extract
atomic intended behaviors, constraints and prohibitions; apply supervisor-authored
Markdown from Job knowledge; obtain supervisor approval of the exact list in
OtterDesk Chat; verify each approved rule independently against
captured implementation; publish an editable Markdown list and evidence table.

The first setup question requires the source code folder with no suggested or
default path. Samples are available only by explicitly selecting their folder.

The five serial logical phases are capture, extract, review, verify, publish. Each phase declares a stock domain-operation block. Domain hooks
retain code-review policy and approval authority. Core owns routing and completion. Workers consume the native block context directly. Core execution is unchanged;
the SDK stages folders using this blueprint's declared directory exclusions.

## Rule contract

Extraction, source-repair and investigation calls send their response schemas
through the SDK's structured-output API. Structural validation cannot replace
exact source admission or supervisor approval. Explicit fake-model execution may
return an empty extraction or Unknown judgments; it establishes no conformance
result and retains the same human review gate.

Verification returns an object containing `decision`; its nested union selects
search, read or finish. Every branch uses explicit action/status types. A root
union must not be sent to strict model routes. Trusted code unwraps the decision
before applying the unchanged source-evidence and confidence checks.

The supervisor's digest-addressed Markdown review document is committed as a
host-readable shared artifact before its Core interaction is published. Replay
verifies identical bytes; private checkpoints keep private permissions.
Editable `rules.md` uses the same host-readable permissions on each replacement.
Final reports use the SDK publication adapter to verify delivery and register
receipt-backed runtime downloads, including the editable rules document.

`knowledge/rules/*.md` contains `## RULE-ID` or `## RULE-ID — Short title` sections
and Markdown statement bodies. Titles are at most 120 UTF-16 units; statements
are at most 4,000 UTF-8 bytes. Exported rules retain their titles and stable IDs.
Each ID is unique across files. Empty files are allowed. A malformed rule file
fails visibly. Augment combines extracted rules and custom rules, with custom
IDs overriding generated IDs. Replace uses only custom rules. An empty effective
list after successful extraction requires human review and publishes no
conformance result. An empty list with unresolved extraction gaps is a failed
extraction: it cannot publish an approval request, consume an older approval,
start verification, or complete as a conformance report. This applies to cached
artifacts and retries as well. A staged `extraction-status.json` records zero
candidates, unresolved and unattempted sections, and available typed diagnostic
codes. Error diagnostics retain only bounded types, codes, stages, retryability
and provider response counts; provider messages, credentials, prompts and sources
are excluded.
Candidates beyond the investigation limit remain visible and receive Unknown
rows after human review of that budget.
Generated IDs are deterministic hashes of document path plus normalized statement;
they are stable when both remain identical, not guaranteed across model rewrites.
Models select immutable source-line IDs; trusted code copies the exact captured
text and physical span. Invalid selections receive focused corrections that
preserve every original statement. Invented handles cannot establish references.
Canonical candidate artifacts and cache entries must pass exact quote/span
validation against the current captured source before admission.

Responses receive at most `review.max_extraction_attempts` attempts per packet
(default and maximum 3). Malformed JSON, incomplete output and persistent
selection errors partition the source into smaller complete-line packets within
the same packet budget and deadline. Successful children survive sibling
failures; partial model responses are never admitted as complete extractions.
Unresolved sections record identity, line range and safe reason in
`extraction_gaps`, then other documents continue. Transport failures receive
bounded retries and backoff. Three consecutive unavailable document packets
open the phase circuit; remaining sections become explicit gaps. Deadline
exhaustion also becomes gaps. Every gap is bound into human review and the
published report. Missing requirements never receive invented judgments.
Draft responses are confidential audit artifacts, not rule or approval authorities.
The complete effective list is `rules.md`; source provenance is in `rules.json`.
Job-scoped candidate caches bind snapshot, document hash/span and extraction
policy and require fresh evidence validation. They never retain approval
authority. Invalid entries are recomputed; optional cache writes cannot block
results. The cache holds at most 2,048 entries of at most 1 MB each.

## Required human review

Version 1.1.0 adds a mandatory review gate. Unattended runs now stop before rule
verification until the supervisor explicitly approves the list in Chat. There
is no configuration option or model response that can bypass this gate.

The review specialist uses SDK `human_interactions` to publish blocking approval
records to Core. OtterDesk's existing conversation interaction stream displays
them and submits Approve/Reject directly to Core. It does not publish legacy
file-ledger requests. The step waits for authoritative decisions; the verification
specialist independently reads them again before creating its model client.

One Core request binds the canonical ruleset digest (including source snapshot
and provenance), review revision, and SHA-256 of an immutable Markdown collection
artifact. The existing conversation stream displays a searchable list of short
titles, complete Markdown details/source references, and a per-rule Markdown
editor. Title pages contain at most 50 entries; search and Approve all cover the
entire list. No rule text is silently omitted. Review artifacts are at most 16 MiB.

Saving an edit sends the existing rule ID, title and Markdown through Core's
bounded `revise` response. The specialist validates it, retains original source
provenance, saves the revised rules and audit, and publishes a new content-bound
review. This never grants approval. A save interrupted between rules persistence
and coordination-plan persistence is reconstructed from its exact Core edit
receipt. Invalid edits preserve the rules and request review again.

Approve all authorizes the entire saved version. The latest Core request must
match that version before verification and report publication. Unsaved drafts,
stale decisions, a prior run, changed local rules, forged approval files or an
audit event alone cannot grant permission. Rejection stops the run. Edits apply
to the current run; exported titled Markdown can be copied into Job Knowledge
for reuse. Unresolved extraction coverage and investigation limits are included
in the hashed review content and remain visible in a scope notice. Accepting
partial scope does not imply missing requirements were found or verified.

Pending reviews share one persisted expiry, at most one hour. Rejection,
expiration, missing decisions or authority failures never authorize verification.
The review step returns only after the saved list is approved. Core cancellation
ends the worker. Duplicate delivery reuses the same request IDs and actual Core
decisions. `rules-review*.json` are audit artifacts, not decision authorities.

## Evidence and judgment

Each rule receives its own bounded model/tool investigation using literal code
search and exact source reads. Only citations read in that investigation can be
admitted; quotes, lines and full captured file hashes must match. File roles are
assigned by trusted code. Names, comments, desired behavior and test definitions
are not execution evidence. Syntax parser gaps and unresolved bindings stay
explicit. Missing matches never prove absence. No repository source or tests run.
Models select evidence IDs from source reads; trusted code copies their text.
Invalid actions, replies and citations receive safe feedback within the turn
budget, allowing query, range and evidence selection changes. Working context
compacts to 24 KB while the full audit history is retained. Large file inventories
are previewed within 24 KB/512 entries; search and read retain the full captured
scope. Three consecutive provider failures end that rule as Unknown. Each
subsequent approved rule still receives its own independent investigation within
the configured rule and verification time limits, even after consecutive failed
rules. Earlier failures cannot substitute an unattempted row for a later rule.
Saved outage placeholders without an investigation are unfinished work and must
be investigated on resume; completed investigations remain idempotent.

Every effective rule has exactly one result: pass, fail or unknown. Pass/fail
requires admitted implementation evidence and model confidence >=0.60. The
static confidence cap is 0.85; Unknown is capped at 0.49, and tool/model/validation
failure or exhausted budgets yields 0.0 with an explicit reason. Original model
confidence is retained when admissible. Scores are uncalibrated assessments,
not measured probabilities. Results always identify `basis=static_review` and
`tests_executed=false`. Requirement conflict, universal claims and runtime-only
properties require human interpretation and usually Unknown.

The Markdown report contains rule, pass or not, evidence with file/line reference
and SHA-256, and confidence 0–1. It includes reasoning, origins, omissions and
limitations. Structured results and captured source accompany the report so a
source checkout changing later cannot silently change historical evidence.

## Safety, storage and evaluation

All source, documentation, custom knowledge and model output are untrusted.
The tool allowlist has only rank/search/symbols/trace/read/finish, with no command, network, edits
or delegation authority. Input and run outputs must be separate. The runtime
stages the selected folder; blueprint capture never derives host destinations.
Artifacts are written atomically before agent output, use deterministic names,
and are reused on duplicate delivery. Per-rule checkpoints bind to the effective
rule and snapshot identity. Knowledge is Job-scoped; new runs capture edits.

Capture has bounded entry, file, byte, format and symlink policies. Excluded
subtrees and files remain explicit. Captured files are UTF-8 and at most 500 KB;
capture is at most 2,000 files/10 MB, custom rules 100 files/500 KB. Default
`review.documentation_scope=current_requirements` excludes documents in case-insensitive
`benchmark-results`, `benchmark_results`, `test-results`, `test_results` and
`playwright-report` directory segments from rule extraction, while retaining
captured text for evidence. `all_captured_docs` explicitly includes these.
`extraction-plan.json` records the selected and excluded document identities,
source snapshot and packet budget before model creation. rules.json and the
final report retain the exact selection and every excluded document.
Extraction uses packets of up to 50 complete lines / a 4 KB target, allowing a
single complete line up to 12 KB. It admits at most `review.max_extraction_packets`
packets (default 512, bounded 1–2048), including adaptive children. The investigation
allowance defaults to 2000 rules and is bounded 1–2000; every candidate remains
visible and requires approval. Excess candidates receive Unknown rows.
Extraction failures and explicitly configured deadlines become reviewable gaps; verification deadlines
mark remaining rows Unknown. Extraction has no default elapsed deadline and requests an
8,192-token output allowance; verification retains 3,500 tokens per request.
Model requests have 90-second deadlines. Bounded retries and adaptation never
substitute deterministic model success. Core cancellation
terminates the executing worker.
Model input packets have a 100 KB ceiling and working tool observations a 24 KB
ceiling. Invalid setup, capture/storage integrity failures and unavailable human
approval remain blocking. Platform staging precedes capture; users select a
clean source scope.

Acceptance: deterministic tests cover complete extraction, custom add/override/
replace, pass/fail/unknown reports, forged and unread references, docs-only
evidence, invalid confidence, missing source, bounded failures, duplicate delivery,
Job knowledge, source immutability, manifest compile and architectural boundaries.
Human-review tests cover pending/rejected/expired states, full preview coverage,
scope and content binding, replay, forged local receipts, Core transport and
the guarantee that no verification model calls occur before approval.
Live model accuracy and full installed/runtime execution are separate opt-in gates.

Non-goals: automatic fixes, repository execution, dependency installation, remote
cloning, formal verification, exhaustive language analysis, complete requirements
discovery, test results or guarantees of conformance/safety.

## Report presentation

`mirrorneuron-web-report-skill` owns common report chrome and component assets.
The blueprint owns its domain-specific views, source scope and evidence semantics.
The web page is local/offline with a minimal header, Actions dropdown, progressive
tabs and a non-modal evidence Sheet. Presentation adds no model calls, source
execution, external sharing, runtime changes or approval authority.
Rendering or handle-publication failures cannot prevent the authoritative
Markdown and structured report from completing. A safe presentation status
records the failure type without provider or source contents.
Publication stages the declared report, rules, captured source and audit artifacts
in the SDK-provided `MN_JOB_OUTPUT_DIR` before returning. Optional static HTML and its
handle are staged separately after rendering. The runtime owns host delivery and
batch run folders; the blueprint never derives or writes a host Downloads path.
The UI extension declares `static_html`, allowing OtterDesk to open the delivered
`web/index.html` after validating its adjacent handle.
The publication result returns the SDK `published_files` manifest for report
JSON/Markdown and the optional page/handle. Native workers export these verified
bytes for the conversation workspace; optional presentation remains optional.

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
