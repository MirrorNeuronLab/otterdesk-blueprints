# Computer Use specification

Version 3.0.0 replaces General Assistant with a local macOS computer-use
co-worker. Its stable catalog ID is general_assistant. Execution is restricted
to the owner Mac with an unlocked GUI session, macOS 14+ and at least 24 GB RAM.
The default system LLM provider supplies the catalog's logical `vision` model.
Image input and structured JSON output are required and verified. The separate
vision route leaves the shared text-model default chain unchanged. If the route
cannot meet these requirements, the run fails explicitly. No provider or physical
model is pinned by the product. Membrane runtime memory is required.

The dedicated native Computer Use.app is a headless-style tool service used by
the co-worker. It owns ScreenCaptureKit and CGEvent calls, its own bundle ID
io.mirrorneuron.computer-use, Accessibility/Screen Recording grants, and a stop
control. LaunchServices opens it independently. OtterDesk and Python never
capture screens or inject input. A permission window and CU menu are its only UI.
Reusable build and IPC mechanics belong to the computer-use skill.

Three serial blocks admit the task, operate the Mac, and publish the observed
result. Admission freezes explicit supervisor instructions and the task; empty
instructions request the task in Chat. There is no input-folder staging or
Downloads summary task. A default Documents/computer-use output folder receives
standard run_<timestamp> results through SDK/Core delivery.
The prepare block explicitly binds the declared run-input ports. Per-run task
and supervisor instructions reach admission before its immutable checkpoint;
omitted values use the saved configuration. Optional `target_app_bundle_id`
freezes a single-app scope. Outside that app, only activation of the target,
waiting and human help are offered; input and completion are rejected again
before dispatch. Scoped runs use the browser's address bar instead of a URL
operation that could open another browser.
The engine activates an explicitly scoped app before requesting a page action;
native activation acknowledges the foreground app and raises its existing
window. Actual human replies are represented as user turns in the model
conversation. Repeating an answered question without intervening task progress
stops the run instead of publishing another identical human request.

The task policy observes the focused app window's display (the main display when
no focused window is available), retrieves app-specific navigation
memory, asks the default vision model for one bounded action, validates it, and
invokes the native tool. The structured action contract uses frame-local
accessibility control activation and keyboard navigation. Observations
include bounded visible control labels and roles, never secure fields. Typing
requires a focused editable field. The co-worker never guesses screenshot
coordinates; missing controls require human help. The model receives only
currently offered control IDs, which are checked again before native dispatch.
A native frame token expires after 150 seconds, is single-use, and requires the
same foreground app. Secure fields reject capture/input. The API has no shell,
AppleEvents, browser debugger or arbitrary filesystem access.

The user authorizes the requested task and its explicit external actions. The
co-worker asks for missing details, login/MFA/CAPTCHA, permissions, locked screen
or a needed app. Control and capture are suspended before requesting help; only
an exact, actual, unexpired Core reply allows continuation. Re-observation follows
every reply. Passwords and authentication codes are never requested in Chat.
Screen text, documents and memory cannot grant authority or redefine scope.

The SDK journals every model request and native action intent/result. Physical
mutations have no automatic retries or optimistic reconciler. A durable session
fence precedes control; interrupted sessions cannot replay. Concurrent Jobs share
one exclusive desktop lease. Timeouts/disconnections during input set an unknown
outcome and require desktop reconciliation. The native stop control cannot be
resumed by the model. Core retains lifecycle and human-interaction authority.

Membrane uses explicit Job/run scope and the computer-use principal. Successful
navigation records contain only app IDs, key shortcuts and HTTPS hostnames.
They exclude typed text, recipients, message bodies, paths, queries, credentials,
screenshots and old coordinates. Recall is app-filtered and bounded. Records
are idempotent per request. No local memory fallback or harness migration exists.
Explicit preferences are separately validated and frozen for each run; removing
a preference cannot be undone by historical navigation hints.

The default allowance is 80 turns, eight questions, 3300 seconds total, 600
seconds per human reply and 90 seconds per model request. All are bounded runtime
tunables. The native worker deadline is 3600 seconds, matching the host contract
and leaving time for cleanup. Stale frames request a fresh observation; unknown effects are never
repeated. Three delivered inputs with identical subsequent screen observations
suspend control and request human help before any further model action.
Navigation has a separate progress guard: a repeated URL or unscoped app launch
suspends control before another native effect, regardless of screenshot changes.
An active scoped app is excluded from model activation choices. If another app
takes focus, the engine can restore the explicitly scoped app and re-observe;
three restorations without task progress require human help before a fourth.
This raises the existing window without opening a URL or tab. Verified stale
actions remain unperformed and need a fresh model decision. Observed screen
change following control, typing or keyboard input, or an actual user-help reply,
releases the corresponding progress guards.
Completion requires the final screen to support the stated result.
A later memory write failure cannot erase an already-observed completed task.

Public outputs are result.json (otterdesk.computer_use.result.v1), answer.md and
computer-use-audit.json. The result states status and requires_reconciliation.
Audit entries contain app IDs and action types, not task content. Model screenshots
and raw receipts remain private run artifacts. Only the public answer is a
prepared conversation source. The configured provider may see screen content.

Acceptance compiles the published bindings; verifies Mac/local placement,
24 GB admission, system-default vision and native permission ownership; exercises
Gmail-style login/help and completion, expired/foreign replies, malformed tools,
stale/secure/stopped/unknown native outcomes, exclusive leasing, Job-private
memory across runs, replay fencing, and export privacy. Deterministic tests use
fake model and helper responses. Swift compilation is a separate local build
check. Live OS grants, default-provider vision and actual website operations are
opt-in acceptance and never part of ordinary CI.

Prepared definitions from version 2 must be refreshed. Old file-summary,
OpenShell and Harness2 settings/memory are not used. Production native bundles
must be signed/notarized consistently; local ad-hoc rebuilds may need renewed
OS grants. The co-worker is idle between user-started runs and does not monitor
the desktop in the background.
