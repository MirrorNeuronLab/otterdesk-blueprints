# Litigation Analyst implementation report

Date: October 8, 2026. Blueprint version: **2.7.0**.

Reference: `OtterDesk_Litigation_Analyst_Interactive_Output_Spec.md` supplied by the
user. Its fictional case and example numbers are design examples, not evidence
for an actual investigation. This update implements a bounded, offline version
of the core investigation flow. It does **not** implement the entire specification.

## Implemented

| Capability | Delivered behavior |
| --- | --- |
| Primary interactive output | `web/index.html` connects Overview, Findings, People & relationships, Chronology, Issues & evidence, Comparisons, Evidence Explorer, Work product, Since last review, Activity & audit and Matter settings. Authoritative data lives in `case/workspace.json`. |
| Shared evidence projection | Views use the same frozen source versions and exact verified character spans. Source observations, inferred assessments and human review are separate. Cached report prose cannot become the evidence authority. |
| Findings and counterevidence | Stable enquiry/section-based IDs, material digests, revisions, origin, support, known contradictory passages, alternatives, limitations, questions and gaps. Known authorized counterevidence remains accessible outside analytical filters. |
| Source inspection | Exact normalized passages with highlighted spans and full available surrounding text; hashes, source identity, original filename, generated locator labels and source status. Original PDFs can open alongside extraction. Other originals download without executing source HTML/SVG. |
| Comparisons | Two equal, expandable source panels. Qualifications require matching identity, material/version, time, terms and context. No automatic accusation of dishonesty or copying. |
| Relationship exploration | Directed address edges and source-unit relationships, explicit/proposed connection distinction, one-hop preview, equivalent node/edge tables, source drill-through and a disclosed display cap. Addresses are never silently merged into people. |
| Temporal graph analysis skill | Added the declared `mirrorneuron-temporal-graph-skill` dependency and real calls to `temporal_path`, `compare_time`, `distinct_occurrences` and `EvidenceHistory`. The round planner can select `temporal_communication_paths`; the collector verifies and retains its exact source headers. Case tools also expose chronology, temporal paths and event-order comparison. |
| Temporal qualifications | Ordered, uncertain and rejected paths remain separate. Closed time windows retain minute/second precision; unzoned dates remain unknown. Paths do not imply delivery, reading, knowledge, material transfer, causation or continuous roles. Bounds: 4 hops, 128 nodes, 49 edges, 256 witnesses. Webpage prepares up to 16 address seeds; the bound case tool can inspect other authorized seeds. |
| Message counting | Explicit, consistent Message-ID occurrence identities; duplicate copies remain source records. Missing IDs and conflicting copies are unresolved multiplicity. Quoted older messages do not create new header events. Daily communication bars and a directed recipient-field table drill through to their source sets, with count definitions and non-additivity caveats. |
| Membrane memory intelligence | Existing immutable original-source intelligence and planner RAW → GRAPH → RAW recall remain active. Published workspace findings add authored `SUPPORTED_BY`, `OPPOSED_BY` and `CITES` navigation, exact original-source references, source basis, gaps and review state. Only finding-required locators are published; whole source bodies are not duplicated into these runtime records. Memory remains navigation, not independent legal evidence. |
| Snapshot-aware history | Core-owned Job `state` contains immutable temporal source-version/email-event receipts and saved finding snapshots. Knowledge revision/first-retained workspace date are separate from event time and do not claim earlier investigative discovery. Wording, support, counterevidence or gap changes increment material revision; earlier reviewed wording requires reassessment. Direct contexts without Job storage disclose single-snapshot mode. |
| Human review | Name, timestamp, disposition, preserved/revised wording, exact material digest and rationale. Decisions remain separate from model checking; reviewer disagreements remain visible and block approved briefing use. Attribution is self-entered, not authenticated. |
| Saved investigation and views | Explicit HTML copy preserves snapshot, filters, selected object, graph selection, saved views and review decisions. Browser navigation restores route/scope/selection. Originals are excluded from saved copies and clearly marked unavailable. No case data is saved in browser local storage. |
| Next-run review import | Optional staged `review_file` accepts bounded `review-decisions.json` from the same matter. Validation rejects malformed actions, missing attribution/timezones, changed decision IDs and another matter. Old decisions cannot approve changed material. |
| Reviewable work product | Human-qualified wording, supporting/contrary evidence and limitations; neutral gap-linked action drafts with closure conditions. Drafts do not send requests, contact witnesses or alter collections. |
| Briefing export | Preview of reviewed findings/source versions/current review attribution, recipient confirmation, balanced evidence and qualifications. Excerpt-only HTML excludes originals, full source text, original model assessment/title, unreviewed findings/questions/gaps, prior review wording, proposed graph edges, unused graph data, saved views and historical changes. Supporting-only views block export. Copies explicitly cannot be revoked. |
| Source-bound output restrictions | Optional authorized source list and handling/privilege flags remove source content, derived counts, graph support and dependent conclusions before page serialization. Mailbox originals containing any excluded member are omitted. Old broader previews/copies are removed when rebuilding the run webpage. Owner audit artifacts remain confidential and are not sanitized briefing packages. |
| Offline rendering and failure states | Local assets, escaped inert source text, hash-bound script CSP, no webpage network requests. Oversized/failed preview removes stale HTML and preserves verified JSON/report outputs with an explicit status artifact. Incomplete execution and extraction coverage remain qualified. |
| Usability | Responsive layouts, visible focus, keyboard-operable buttons/native dialogs, accessible tables for graph/chart inspection, explicit global AND filtering with sender OR recipient inclusion, reset and one-sided warnings. This is not a WCAG conformance certification. |

## Partial or not implemented, and why

| Specification area | Current limit | Reason / required next work |
| --- | --- | --- |
| Living multi-user investigation / Share View | No authenticated sharing, live role enforcement, server-backed autosave or concurrent review synchronization. | The co-worker is a bounded batch workflow producing local files. These require a declared authenticated service, matter-specific authorization and server-owned revision/audit semantics. A local file is not advertised as private workspace authentication. |
| Matter roles and dynamic permission revocation | Source-bound owner projection and sanitized briefing export only. Full owner JSON/audit files remain confidential. | No identity/session/permission service exists in this blueprint. OS file access and already-exported copies cannot be revoked by browser filters. |
| People profiles and identity correction | Observed address names stay unresolved; no automatic merge, split or corrected identity recomputation. | Safe correction needs a reversible, source-backed identity revision ledger and affected-result invalidation. The temporal skill does not supply that identity policy. |
| Full typed person/organization/material/event graph | Addressing and legal source structure/proposals are available; employment, account-to-resource access and material/version matches are not extracted. | Existing trusted adapters supply email headers and clause structure. New record-specific adapters and reviewed identity/material mappings are needed; model co-occurrence would not establish these stronger relationships. |
| Exposure indicators | No person-by-material matrix or inferred “who knew what” result. | Delivery, access, actor mapping, document identity and statements of review need separately typed source records. Current addressing alone cannot populate stronger categories honestly. |
| Full factual chronology | Email header lane, uncertainty and first-known dates only; no role/access/development/testimony/procedural lanes or disputed-sequence overlay. | Requires exact event-specific extraction contracts, reported-event versus testimony-date separation and reviewed identity/role intervals. |
| Full issues / claim chart | Factual question/support/counterevidence/gap matrix only. No jurisdictional elements, claim construction or legal-strength percentages. | No counsel-maintained definitions, jurisdiction/context or framework versions were supplied. These must be entered and reviewed, not invented. |
| Advanced contradiction and lineage analysis | Source comparison and exact normalized version checks; no confirmed discrepancy workflow, third-source panel, near-duplicate model, family browser or lineage determination. | Requires comparison-specific review dispositions, original family identifiers and separately validated similarity/lineage evidence. Similar text is not an origin or transfer finding. |
| Universal original-source viewer | PDF/original download plus normalized text; no PDF region alignment, transcript official page-line jump, workbook cells/formulas/hidden state, OCR alignment, translation verification or audio/video timecode viewer. | Current normalization does not retain all required format-specific coordinates and structures. Parser/viewer contracts must preserve them before presenting official citations. Generated character offsets stay labeled. |
| Full communication BI | Daily bars and recipient-field table with exact source drill-through; no graphical matrix heatmap, collection/custodian coverage heatmap or issue/review distribution chart. | Custodian, collection-plan, thread/family and detailed processing/review metadata are not present. Missing collection intervals cannot be drawn as zero activity. |
| Gap dependency map / witness preparation | Linked findings/questions, closure conditions and copyable neutral action drafts; no visual dependency map, editable readiness-aware witness outline, owner/target editor or automated topic invalidation. | Requires durable preparation/action objects and explicit typed dependencies, beyond model follow-up strings. No court deadlines or accusatory questions are generated. |
| Financial scenario BI | Unavailable unless separately implemented with reviewed inputs. No damages estimate, waterfall, sensitivity chart or scenario approval. | No actual financial records, mutually exclusive categories, currency/date basis, methodology or expert/counsel review were supplied. Fictional D011/D012 values are not case inputs. |
| In-page case-record model Q&A | Literal available-text filtering and source navigation; analysis questions continue through the co-worker chat's existing Membrane-backed path. | A frozen page has no authorized model/context RPC or live cancellable task service. It cannot pretend that a browser text filter is semantic question answering. |
| Full historical snapshot browser / changes scheduler | Previous authorized snapshot comparison and preserved review history; no arbitrary old-snapshot navigation, sentence diff or incremental affected-region scheduler. | Historical original-version hydration and an explicit dependency scheduler need additional contracts. Current immutable revisions do not silently rewrite old output. |
| Approved offline package with originals | Approved excerpt-only briefings; run owner package can inspect held originals. Saved copies omit originals. | Per-recipient source release, redaction of all derivatives/page images and approval of original inclusion need a dedicated export policy. No decorative redaction is claimed. |
| Cancellation inside webpage | Partial/incomplete execution state is displayed; existing workflow cancellation remains in runtime. No page pause/cancel button or progress stream. | Offline output has no live execution-control channel. A working-looking control would not actually stop the co-worker. |
| Perspective controls / richer local filters | Literal text, address, event-date and source-set filters; no party-perspective tuning, issue/review/source-type selectors or full visual undo history. | Requires explicit analytical-question policy and additional typed metadata. Counterevidence is preserved under current filters. |
| Accessibility certification | Keyboard equivalents, focus and narrow/wide checks delivered; complete WCAG 2.2 AA audit not performed. | Formal screen-reader, contrast, zoom and assistive-device evaluation remains needed. |
| Fictional acceptance fixture | The spec's 1,248-record corpus, 12-message sample and $126,000 scenario were not injected into production output. | The document provides illustrative examples, not a complete source-backed fixture. Tests exercise the mechanics with synthetic local records rather than fabricated matter totals. |
| Installed/live co-worker deployment | Source blueprint updated; no existing hired Job was replaced, installer reset, release published or real matter investigated. | Installed Jobs retain their staged implementation. Deployment needs matching published/local SDK/skill dependencies and explicit update of the selected Job. Live model and native Linux graph execution were not certified by these checks. |

## Validation

- **94 litigation checks passed**, including 12 new workspace checks; one opt-in
  Linux Docker/RGX test skipped. One catalog-dependent test was deselected in the
  focused run after separately confirming it fails on an unrelated existing
  `vc_assistant/payloads/:memory:.ses` unsafe package path.
- **6 litigation dependency/context packaging checks passed**, covering source and
  binary staging contracts through mocked preparation.
- **1 OtterDesk static-output UI contract test passed**; generated run handles
  declare the static adapter and point to the emitted webpage.
- Local Chrome automation exercised finding → exact support/counterevidence →
  source comparison → temporal path → chronology → attributable review → saved
  view/copy → approved excerpt briefing. It also checked counterevidence outside
  filters, one-sided export blocking, excluded originals/full source bodies,
  600/1360-pixel resizing, no page errors and no webpage network requests.
- JavaScript syntax and scoped `git diff --check` passed.
- Broad repository run: **644 passed, 118 failed, 37 skipped, 10 errors**. Failures
  include the existing unsafe VC package path, other domain contracts and stale
  dependency/test adapters. The catalog contract subset has 2 passes and 3 failures
  from that unsafe path. This update does not establish a green repository-wide CI
  baseline or claim that every broad failure was independently baseline-tested.
- Membrane tests use deterministic in-process transport. Native temporal operators
  are exercised directly. No live Membrane/model deployment, real case, Windows
  browser, published wheel availability or Linux RGX execution was verified.

## Files and rollout

New domain modules: `temporal_evidence.py`, `workspace_projection.py`,
`workspace_graph.py`, `workspace_history.py`, `workspace_memory.py`,
`workspace_web.py`, and local `workspace_assets/`. The report publisher, source
header normalization, bound case tools and child-round planner/collector integrate
them. Descriptors declare temporal skill dependencies, Job state, outputs and the
optional review input. README/SPEC/conversation knowledge describe actual limits.

Existing unrelated edits were preserved. There was no commit, release publication,
installer reset or modification of real case sources. Existing hired co-workers
need the updated staged blueprint before they produce this new output.
