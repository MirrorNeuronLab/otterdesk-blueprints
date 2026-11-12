# Blueprint conversation profiles

All published packages expose optional app guidance at `payloads/prompts/conversation.json`, with schema `otterdesk.conversation_profile.v1` and the exact manifest ID. The local Computer Use and GTM packages use the same contract without being published by `index.json`. It is an OtterDesk asset, not a runtime extension or second catalog. It describes responsibility, evidence boundaries, limitations, allowed instruction kinds and eleven conversation stages. OtterDesk combines it with authoritative Job state, pending input, safe confirmed answers and selected run evidence.

| Blueprint | Saved instructions | Work and evidence boundary |
| --- | --- | --- |
| Computer Use (local) | Communication and future task rules | Frozen task and observed screen outcome; private navigation and visual memory do not prove a current action succeeded. |
| Procurement Manager | Communication and future review rules | Post-intake analysis context; no public-query leakage, ranking or transaction authority. |
| Architecture Advisor | Explanation preferences | Source snapshot and configured review files retain scope authority. |
| Code verifier | Explanation preferences | Exact Core rule-list approval and Job rule knowledge remain authoritative. |
| Litigation Analyst | Explanation preferences | Matter handling, legal review and source provenance retain authority. |
| VC Assistant | Explanation preferences | Scoring policy, public research permissions and company evidence remain unchanged. |
| Drug Discovery Research Assistant | Explanation preferences | Native scientific pipeline and computational scores remain unchanged. |
| CT reader | Explanation preferences | Native CT request unchanged; saved research report is a run-linked prepared source. |
| Mac security investigator | Explanation preferences | Capabilities-only Chat; private evidence remains in local ledger/Membrane. |
| CCTV Operator | Bounded Job caption history | Secure camera source, monitoring goals and completed NVIDIA video-window observations. |
| ROS AMR Controller | Existing bounded Job memory | Existing zone aliases and restrictive rules; live motion and operation receipts. |
| Web Lab Operator | Explanation preferences | Frozen Markdown, observed simulation state and saved checks; no physical lab or assay evidence. |
| OCR worker | No app-managed persistent instructions | Saved per-file text, page regions, source coverage and explicit failed/skipped inputs. |
| Transcription worker | No app-managed persistent instructions | Saved transcripts, complete chunk coverage and verified optional alignment; speaker identity is not established. |
| GTM planner (local) | No app-managed persistent instructions | Public evidence, idea review and bounded aggregate status; no contacts or inbox contents. |
| GTM executor (local) | No app-managed persistent instructions | Exact-email review and observed provider receipts; uncertain sends require reconciliation. |

The optional app-managed `inputs.payload.supervisor_instructions` list has at most 50 unique records, 1,000 characters per text and 16,000 JSON UTF-8 bytes total. New runs capture supported work rules once. Later edits and forgetting do not change accepted runs or historical evidence. Ordinary corrections and dialogue never become long-term instructions implicitly.

Existing Membrane source intelligence and TextMemory consumers keep their current ownership and enablement. No chat transcript, credentials, private computer-use memory or arbitrary input files are copied into conversation memory. Missing context is explicit; earlier reports remain historical. Bounded domain actions and memory keep their original runtime planner and validated receipts.

Validation uses the catalog inventory in `index.json`: `tests/test_conversation_profiles.py`, each domain's offline suites, and the full catalog tests. The profile suite also names the three local packages explicitly; it does not publish them. The desktop's `test:blueprint-conversations` command runs eight fake-inference contract cases per published blueprint. Those checks establish context delivery and isolation, not live language quality, clinical/scientific validity or robot safety qualification.

## Reply behavior

Each package owns its setup prompt, stage profile and installed conversation
guide. Answer the current question first in plain language and sentence case,
usually with one to three short paragraphs. Preserve confirmed answers and ask
only for a needed answer or actual review decision. A follow-up should not replay
the welcome, setup checklist or complete report handoff. Technical detail belongs
where it helps the supervisor decide or resolve a problem.

Setup help uses `reply_to_setup` once with `changes=[]` and no mode. An explicit
supported source selection or setting answer may draft only declared fields.
Paths and credentials stay in dedicated controls. Defaults and examples are not
confirmed answers. The app owns saving and launch; after its final required
answer, prompts must not introduce another Save or Start confirmation. Domain
review gates, such as the exact Code verifier rules and GTM email approvals,
remain separate and authoritative.

Status replies distinguish preparation, observed progress, pending decisions and
verified results. A failure explains what did not complete and one supported
next check. Missing context cannot justify invented progress, findings or links.
Results lead with the useful takeaway, keep material uncertainty beside its
supporting evidence, and distinguish current work from historical reports.
The Mac security role retains capabilities-only Chat, and live services retain
their separate command-completion and service-lifecycle semantics.

## Onboarding and result handoffs

Each published role carries its own conversation content in three existing
surfaces: the stage profile for native Chat, `extensions/ui.json` for setup copy
and starter questions, and `knowledge/` for the installed manual and reference
retrieval. The manual includes the essential input and result guidance directly
and links to `conversation_guide.md`. Existing isolated worker copies of that
guide stay identical. Every role declares welcome copy through the existing
setup-guide contract, including roles whose defaults need no setup confirmation.
Seven guides were previously generated by the SDK from input contracts. Their
authored versions retain those exact fields, defaults, sample availability and
sample/real values while supplying role-specific copy. Tests compare the
declarations with the existing SDK projection to prevent hidden settings or
changed sample paths; normal configuration and startup behavior are retained.
Their sample cards name the actual example, explain what it demonstrates and
describe the expected handoff without presenting it as a completed result.
No execution code, runtime schema, tool permissions,
sample-mode availability, configuration defaults or approval gates change.

An introduction explains the responsibility, the useful deliverable and one next
missing input in two or three short sentences. It keeps confirmed answers and
does not replay a greeting on follow-ups. Optional settings and technical detail
stay secondary. Setup retains each role's existing launch behavior, including
CT's launch on the final required answer and Microduck's service startup on hire.

An initial result handoff answers the agreed question, points to available saved
work, explains evidence and material limits, and identifies one next human
decision. Follow-ups answer the requested point instead of repeating the entire
handoff. Status alone cannot establish a finding or delivered file. A live
service reports observations or command outcomes without declaring the service
finished. Missing evidence, historical results and synthetic material remain
explicit.

| Co-worker | Starting experience | Result explanation |
| --- | --- | --- |
| Computer Use (local) | Give a Mac task; optional instructions and native screen/input permissions use their existing controls. No synthetic desktop. | Observed result against the task, action audit and any unfinished or uncertain action. |
| Procurement Manager | Choose the existing fictional offline quote sample or a real purchasing brief. | Comparable known costs, requirements, missing terms and assumptions; no supplier contact or order. |
| Architecture Advisor | Choose a local source folder; the synthetic repository is an ordinary folder-selection option, without a sample button. | Priority finding, affected components, source support, counterevidence and proposed engineering validation. |
| Code verifier | Choose source/docs and rule source; the bundled synthetic folder uses the same approval flow. | Pass/Fail/Unknown coverage, exact approved rule, evidence and an engineering check. |
| Litigation Analyst | Choose the public synthetic EMC-2 download or authorized matter sources. | Draft support and counterevidence, chronology, partial coverage and a counsel-review question. |
| VC Assistant | Keep the synthetic startup packets or configure approved company folders. | Dated claims, method assumptions or disagreement, missing diligence and a human review question. |
| Drug Discovery Research Assistant | Review BACE1 and synthetic seed inputs or approved targets and research profile. | Cycle, candidate identity, actual ranking basis, stage coverage and missing scientific validation. |
| CT reader | Upload a de-identified volume and choose anatomy; no bundled scan. A format walkthrough needs no inference. | Faithful explanation of saved wording, negation, uncertainty, crop and research limits. |
| Mac security investigator | Automatic bounded local collection; no source upload or runnable sample mode. | Report availability and generic guidance on coverage; private findings stay in the local report. |
| CCTV Operator | Secure approved RTSP/RTSPS camera and optional visible goal; no sample camera. | Completed captions and reviewed snapshots when available, capture intervals, citations, index coverage and uncertainty; preview is separate. |
| ROS AMR Controller | Included warehouse simulation with approved zones and fresh status. | Requested zone, observed arrival/failure/unknown and restrictions; admission is not arrival. |
| Web Lab Operator | Synthetic dilution series or Markdown text/file with explicit inventory, operations and final volume goals. | Observed simulated steps, source adaptations, final checks and available replay; no experimental validation. |
| OCR worker | Source folder or supplied newspaper clipping, with optional text grouping. | Completed/failed/skipped counts, per-file text and page comparison when published; partial coverage stays explicit. |
| Transcription worker | Audio folder or full 50-minute Bdb001 recording on compatible Blackwell hardware. | Markdown coverage first; optional playback requires verified alignment, and speaker labels are local to a chunk. |
| GTM planner (local) | Website and goal, with co-worker membership managed in Collaboration. | Source-backed idea and actual review/handoff status; planned metrics are not results. |
| GTM executor (local) | Authorized contacts through the file control, provisioned inbox and secure credential. | Exact-email review or aggregate observed outcome; acceptance is not delivery, and unknown sends are not retried. |

Sample inputs reduce the need to supply personal material; they do not remove
model, network or hardware requirements. A walkthrough describes the experience
without executing work. Sample buttons are offered only where the existing setup
contract declares one. The offline procurement quote case is distinct from the
configured edge-AI market comparison, and Mac history fixtures remain tests only.

Stage strings stay within the desktop's 1,000-character normalization limit.
Evidence and limitation fields are arrays of bounded strings, including for Web
Lab Operator; a nonempty string is not accepted by the desktop reader. OCR,
transcription and both GTM packages now provide profiles and linked guides without
enabling a new persistent-instruction feature. The profile schema and eleven
stages are unchanged. Tests check catalog coverage,
normalization bounds, manual links and existing staged guide equivalence. They
cannot establish the quality of live model prose.

Updated package guidance applies when the package is loaded. Knowledge seeds
are copied on Job initialization; existing Job knowledge needs an explicit
supported import or update. Editing this catalog does not overwrite a hired
co-worker's knowledge, rewrite a saved report or reset a running Job.

## Validation on 2026-11-11

- All 35 conversation-profile tests passed across the 13 published and three
  local packages. Setup fields, defaults and sample/real choices were checked
  against the previous authored contracts and preserved.
- The desktop's fake-inference evaluation passed 104 published-package cases
  and 24 cases using an isolated catalog of the three local packages. These
  checks validate context delivery and isolation, not live response quality.
- The OCR and transcription suites passed 40 and 27 tests respectively.
- The full catalog suite reported 1,467 passes, 39 skips, 64 failures and 61
  errors. Its remaining issues include tests for the removed Research Assistant,
  outdated catalog expectations, unavailable `mn_api.blueprints` and `pylabrobot`
  dependencies, sandboxed local listeners, and a dependency version in a saved
  planning file being treated as a deployment address.
- The source witness was refreshed only for 50 changed conversation assets in
  its existing package inventory. All 34 other source-hash differences were
  verified to exist in Git HEAD; unrelated runtime and inventory baselines were
  preserved. The full run loaded the earlier witness at collection time, so the
  final changed-asset hashes were checked separately.
- `git diff --check` passed. No live model-quality evaluation, live domain work
  or update to an existing hired co-worker was performed.

## Validation on 2026-10-28

- The final focused blueprint gate passed 63 tests, including stage bounds,
  authored welcome coverage, manual links, staged knowledge copies and preservation
  of the previously generated setup contracts.
- The desktop's fake-inference evaluation passed 112 cases across all 14 roles.
  A separate SDK-to-desktop round trip checked all 14 first-hire welcomes and
  preserved editable fields, defaults, sample/real values and readiness.
- The full catalog run reported 1,580 passes, 41 skips and 12 failures. Eleven
  failures came from sandbox restrictions on localhost listeners. The remaining
  failure exposed the Mac output field being hidden by an authored guide; its
  original generated contract was restored and guarded across all seven affected
  roles. The final 32-test rerun covering every failed case passed with loopback
  access. The seven new contract-preservation cases are included in the focused
  gate above.
- `git diff --check` passed. Runtime, SDK, desktop source and blueprint execution
  code were unchanged. No live model-quality evaluation or live domain work was
  performed.
