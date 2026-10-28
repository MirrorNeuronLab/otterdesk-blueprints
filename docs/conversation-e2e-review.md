# Conversation experience E2E review

Status: incomplete. All 14 co-workers have been attempted and their available
conversation surfaces reviewed. Runtime preparation, desktop conversation
routing and remaining answer-quality findings prevent full journey approval.

The suite exercises the real Electron GUI, API, IPC and installed runtime.
Direct desktop/setup replies use the cached CPU conversation model. Job replies
use their own configured model path and can inherit the fake LLM setting. The
default domain execution uses fake LLM/skills and synthetic inputs; it does not
establish domain accuracy or genuine language quality from a placeholder. A
separate Mac check used normal Job replies with fake skills: report delivery and
question dispatch passed, but the answers did not explain coverage or limitations.
Runtime and desktop source remain unchanged. The desktop checkout already
contained unrelated changes; these findings describe that tested checkout,
not a pristine release build.

Run instructions are in [the E2E harness guide](../tests/e2e/README.md). Local
screenshots, transcripts, prompt digests and output receipts are under
`blueprint-experience/` in this task's visualization folder. The recorded
attempts are `matrix-first-pass/`, `matrix-reviewed/`,
`matrix-remaining/`, `final-targeted/` and `mac-normal-replies/`; earlier focused
probes retain the before/after evidence. All 14 identities have been attempted,
but their complete journeys are not all verified.

## Verified findings and changes

Help questions initially failed for General Assistant and Financial Advisor:
the real model drafted a setting that was not declared, so the reply was
rejected. Role-specific `payloads/prompts/setup.md` assets now show the exact
explanation-only tool shape with an empty change list and no source selection.
These assets use the existing `setup_guide.prompt_file` contract. Repeated real
GUI questions for both roles produced replies with no draft changes or mode
selection; confirmed values were preserved.

The reviewed replies still asked for ordinary Chat confirmations or pasted paths;
General Assistant also exposed an internal context key in an earlier attempt.
The app chooses onboarding or configuring from its stored source mode, which can
already be initialized before an explicit source choice. The final frozen runs
used configuring for General Assistant, Architecture Advisor and Microduck, and
onboarding for Procurement. Observed setup-note and normalized profile digests
matched current source for all four. Both stages now distinguish a first welcome
from help, point to existing controls and handle preparation failures separately.
General Assistant and Architecture Advisor have explicit empty-change JSON
examples. Final GUI reruns still showed premature readiness claims, requests for
pasted paths or mixed sample/default scenarios; empty draft changes alone do not
establish answer quality.

Initial welcomes and sample previews describe the mission, required input,
declared sample option and expected handoff. Nine sample outcome previews now
explicitly describe future work, such as “After the sample review completes…”.
After that last copy edit, all 14 SDK catalog records passed the desktop's actual
normalizer and initial-welcome projection without losing their text. This was a
deterministic consumer check, not another model or GUI run. Fields, defaults,
sample availability and sample/real values remain unchanged.

Model-only probes use the same cached CPU engine and setup assistant with authored
synthetic context, without a GUI or Job. They are supplementary evidence only.
They still produced unsupported “I'll start” language or answered a failure
question by requesting the source again. A shorter General Assistant prompt also
drafted the default task on a help question; its explicit empty-change JSON
example was restored. The harness now rejects any help draft, confirmation of a
default, source selection or leaked internal key. Remaining language problems
are open findings, not verified fixes or successful result handoffs.

The hiring notification can cover the composer Send button and remain present.
The harness uses its normal dismiss control to continue, rather than forcing a
click. This desktop issue is recorded, not fixed by blueprint content.

## Journey coverage

| Blueprint | Verified experience so far | Remaining evidence |
| --- | --- | --- |
| General Assistant | Welcome at both widths; final real help reply with no draft changes. Sample launch attempted. | Preparation fails at HostLocal Python environments with `MN_EXECUTION_FAILED`; completed work and final explanation unavailable. Help still treats default inputs as configured and implies it can proceed. |
| CCTV Operator | Welcome and secure-source setup inspected. | Setup messaging was unavailable and Job definition submission failed with `MN_NODE_UNAVAILABLE`; normal workflow and observation review remain unverified. |
| Drug Discovery Research Assistant | Welcome and real help inspected; no draft changes. Preparation reached terminal `MN_NODE_UNAVAILABLE`. | Help requests another confirmation of the default task. A started cycle, actual result and explanation remain unverified. |
| Architecture Advisor | Welcome at both widths; final real help with no draft changes. Preparation reached terminal `MN_NODE_UNAVAILABLE`. | Help still requests a pasted source path. Completed review and explanation are unavailable. |
| Code verifier | Welcome inspected. The frozen rerun reached terminal preparation failure `MN_NODE_UNAVAILABLE`; its help question was rejected as uninterpretable. An earlier mutable-source attempt reported a missing compiled block lock. | Exact rule approval, completed results and explanation. |
| Litigation Analyst | Welcome and real help inspected; no draft changes. Preparation failed with `MN_NODE_UNAVAILABLE`. | Source selection, completed investigation and result explanation. |
| VC Assistant | Welcome and real help inspected at both widths. Synthetic sample Job prepared and its run started through GUI; fake modes verified. | Public-research retries prevented terminal work within the 12-minute observation budget. The owned run was cancelled and cleaned up; no completed-result explanation was reached. |
| Financial Advisor | Synthetic sample completed through GUI; both fake modes verified. Downloaded `result.json` and required `financial_advisor_report.md` matched size/hash receipts. Both real Job questions dispatched and completed. Answers discussed missing income evidence, a pending transaction, fees and fixture prices; evidence disclosure and resized layout inspected. | Opening help still implies work will start before source choice. The initial result is long and its limitation follow-up repeats other findings; workflow success is not full language-quality approval. |
| Research Assistant | Welcome and real help inspected; no draft changes. Preparation failed with `MN_NODE_UNAVAILABLE`. | Completed evidence packet, any exact-packet review, result and explanation. |
| Procurement Manager | Welcome and real help inspected. Preparation failed with `MN_NODE_UNAVAILABLE`. The prompt now names the actual Atlas/Cedar/Delta sample; the rerun still combined it with the default market brief. | Scenario distinction remains an open language finding; completed comparison and explanation are unavailable. |
| Microduck Controller | Simulator loaded through the workspace; fake modes verified. Revised setup help described duck controls. Its live state reply deferred until the simulation ends, and the new observer confirmed no Job-question dispatch. | Live state explanation and observed command/result are unverified. The stricter test now fails that handoff. |
| ROS AMR Controller | Welcome and real help inspected. Preparation failed with `MN_NODE_UNAVAILABLE`. | Help incorrectly presents simulation and sample as separate options. Warehouse readiness, navigation/result and explanation remain unverified. |
| Mac security investigator | Fake-mode workflow completed but placeholder answers failed the stricter check. A separate normal-reply run verified required `report.md` (51,495 bytes), two completed Job-question dispatches and non-placeholder replies. No private findings appeared in visible replies. | Replies ask which report format the user wants instead of explaining coverage or the key limitation. Transport passes; semantic review fails. The capabilities-only conversation boundary and disabled RAG remain intact. |
| CT reader | Welcome inspected; help was rejected as uninterpretable. Preparation failed with `MN_NODE_UNAVAILABLE`. | Synthetic NIfTI upload, anatomy, saved research report and explanation. |

## Environment and test controls

Initial checks found two healthy runtime nodes and no active runs. SDK metadata
on both nodes reports `mirrorneuron-python-sdk` and common version
`1.4.1.dev28`. Node health alone has not established that the required owner
and preparation operations succeed: CCTV's test operation specifically reports
that its resource owner is unreachable.

The test runner includes all 14 published identities, including General
Assistant. It uses the GUI source controls and observes authoritative run/output
receipts. A help failure is retained as a test failure while independent later
phases may still be inspected. Preparation failure is never counted as a
completed journey.

The first driver also waited too long after a failed hire removed the co-worker
from the team. The harness now observes the actual install IPC error. It waits
for the original preparation operation before source selection, avoiding an
accidental retry from a later setup action. The ten-case remaining matrix
finished with seven failures and three nominal passes. Manual review rejected
Microduck's generic wait reply and Mac's fake placeholder. The final frozen
eight-case rerun passed Financial Advisor and failed seven cases under stricter
checks. The separate normal-model Mac check passed automated transport/output
checks but failed manual answer-quality review.

An interrupted focused probe left one test-owned, unrun Financial Advisor Job;
its recorded receipt was reconciled and that disposable Job was deleted before
another launch. The runner now performs receipt-based cleanup outside the test
worker as well as inside it. All suites have ended and their test Jobs were
cleaned up; the final Job inventory contained only the supervisor's pre-existing
VC Job, which was preserved.

Focused blueprint checks pass, including prompt-file paths, size bounds,
knowledge-copy consistency and preservation of generated setup controls. These
checks supplement the GUI evidence and cannot replace the remaining journeys.

The final focused contract gate passed 53 tests after the last copy edit. The
full Python suite reported 1,597 passes and 41 skips, with one failure and one
setup error. The Microduck
asset assertion needed to include the newly declared `setup.md`; it was updated.
Architecture's snapshot guard caught a prompt edit I made while its test was
compiling.
Both checks passed in an isolated rerun with blueprint content held fixed.
JavaScript syntax and `git diff --check` also pass. This does not make the live
catalog run green.

## Remaining boundary

Healthy node inventory did not resolve owner submission or HostLocal environment
preparation failures. The desktop's active-run guard answered Microduck's state
question without dispatching it to the running service; Financial Advisor's
completed dispatches provide a positive control for that observer. The generic
Job responder does not consume the desktop conversation profile, and Mac's
disabled RAG prevents that path from retrieving its conversation knowledge.
These findings cannot be repaired through wording alone. Enabling broader
retrieval, changing runtime execution or bypassing the normal GUI path would
exceed this blueprint-only conversation task. No such changes were made.
