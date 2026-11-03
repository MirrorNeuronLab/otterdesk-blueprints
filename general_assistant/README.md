# Computer Use

Give this co-worker a task in ordinary language, such as “Using Gmail, send an
email to alex@example.com with subject Lunch and body: Can we meet tomorrow?”
It operates apps and websites on your Mac, asks in Chat when it needs help,
and checks the screen before reporting the result.

The co-worker lives in OtterDesk. Its computer tools run in a dedicated native
**mn computer use.app** helper, used like a headless CLI service. The helper has no
separate chat or task UI; a small permissions window and CU menu provide setup
and an immediate stop control. OtterDesk does not perform screen capture or
input injection.

## Requirements and setup

- macOS 14 or later, at least **24 GB system RAM**, two CPU cores and 16 GB disk.
- An unlocked, logged-in local desktop with the target window visible.
- The system's configured **default LLM provider**, with the catalog's logical
  `vision` route supporting image input and structured JSON output. This route
  leaves the shared text-model default unchanged. An unavailable or unsupported
  vision route fails explicitly.
- Membrane v2 and its SDK context extra for private navigation and image memory.
  The runtime prepares EmbeddingGemma 2 for image encoding.
- Adding this co-worker downloads its signed, notarized native helper from GAR.
  Installing OtterDesk or the runtime does not install it. Xcode is not required.
  For manual setup use
  `mn-computer-use setup`; `mn-computer-use doctor` verifies the bundle.

Start a task and grant **mn computer use**, not OtterDesk, **Accessibility** and
**Screen Recording** in System Settings → Privacy & Security. Its stable bundle
ID is `io.mirrorneuron.computer-use`. The helper is launched independently by
LaunchServices. No Automation, AppleScript or browser-debugger grant is needed.
Reinstalling reuses the verified current helper. An unsuccessful update preserves
the previous app; stop active computer-use tasks before updating.

Setup accepts optional Instructions and an Output folder, defaulting to
`~/Documents/computer-use`. Leave Instructions empty to give the task in Chat.
Saved instructions apply unless an explicit per-run task overrides them. There
is no input-folder requirement and no default task that reads Downloads.
The prepare step forwards the declared task, optional app scope and supervisor-instruction run ports
before freezing admission, so a per-run prompt takes precedence over saved setup.

```bash
mn blueprint run ./general_assistant \
  --set 'inputs.payload.task=Open https://example.com and tell me the page heading. Do not submit anything.'
```

`examples/demo.json` contains that read-only browser walkthrough. There is no
synthetic desktop or automatic login. The stable catalog ID remains
`general_assistant`; its displayed name is Computer Use, version 3.0.0.

## Conversation and control

If Gmail needs sign-in, an app needs opening, permissions are missing, or a task
lacks details, the co-worker asks one focused question in Chat. It suspends
screen capture and control while you take over, waits for the actual reply,
then observes again. Enter passwords, MFA codes and CAPTCHA responses directly
in the app or browser. Never paste them into Chat. A reply does not itself
prove sign-in or task completion. Expired, rejected, cancelled and foreign
replies cannot continue work.

Explicit requests authorize their stated external actions, including sending
an email. Missing recipients, content or scope are clarified before proceeding.
Website content and received messages cannot authorize unrelated actions.
Use the helper's **CU → Stop computer control** at any time. This cannot be
undone by the model; a new task is required. Standard pause/resume/stop and Job
MCP supervision remain owned by Core.

One task controls the Mac at a time. Capture crops to the focused app window on
its display when available. Each input action needs a fresh screenshot and the same foreground app.
After three inputs produce identical screens, control pauses and Chat asks for
help. Repeated navigation to the same page or app pauses before another native
action, even when new tabs change the screenshot. If another app takes focus,
an explicitly scoped app can be restored at most three times without progress
before asking for help. App activation raises the existing window. The co-worker uses the existing browser page and navigates only when
the task needs a different page. Observed progress after task input or actual user help permits later
navigation. Secure password fields block capture and input.
The co-worker uses named accessibility controls, Unicode typing, shortcuts,
HTTPS navigation and app opening. It asks for help when a needed control is
unavailable, and uses screenshots to check the result. Typing names a current
editable field; the helper focuses and verifies that exact field while posting
text. The native API exposes no shell or arbitrary filesystem tool.

## Memory and results

Membrane recalls successful navigation patterns for the current app, privately
within the hired Job. These hints help avoid rediscovering navigation on later
runs. Current screens remain authoritative: memory never reuses coordinates,
assumes an account is logged in, grants permission or supplies credentials.
Only observed navigation keys, app IDs and HTTPS hostnames are retained; typed
text, email recipients/bodies, URL paths/queries and screenshots are excluded from
these navigation records. Failed tasks add no successful lessons. Explicit preferences remain
managed separately through Chat > Memory and are frozen at run admission.

Visual memory uses **EmbeddingGemma 2** to encode actual screenshots from completed
work into 768-dimensional vectors in Membrane. It recalls up to three similar
layouts for the current app, with historical field labels and roles. Current
controls are always checked again; memory contains no executable actions, old
control IDs or coordinates. Repeated queries for an unchanged control layout are
cached after the original sources and images are revalidated.

Original images remain in private Job storage at
`state/computer_use_visual/`; the local catalog holds locators, not vectors.
Screenshots can contain visible email or other confidential screen content.
The default limits are four states per completed run, 32 retained states and
64 MiB of image assets. At capacity, recall continues and new learning reports
`capacity_reached`; existing images are preserved. Failed tasks never publish
their buffered images. A later indexing failure preserves task completion and
reports the memory failure, so a completed send is not repeated to teach memory.

Results are `answer.md`, `result.json` and `computer-use-audit.json` in the
standard `run_<timestamp>/` output folder. The audit records action types and app
IDs, without typed content. Screenshots and model receipts stay in private run
artifacts; selected successful images also enter private visual memory. They
are never exported to the output folder.
The public answer is available to the existing Job responder through prepared
Membrane sources. Screen content may be visible to the configured model provider.

Desktop work executes once. There are no recursive probes or automatic action
retries. A disconnect during a mutation has an unknown outcome; inspect the
desktop before retrying so an email or other action is not duplicated. Completed
checkpoints replay without redoing work. Interrupted, uncommitted sessions need
reconciliation. Default limits are 80 model turns, eight help requests, 55 minutes
total, ten minutes per human reply and 90 seconds per model request. The native worker has a one-hour deadline,
leaving time for cleanup and publication.
After a recognized Send, Submit, Publish, Purchase, Pay or Delete control, or a
send shortcut, the co-worker can only observe, wait, ask for help or finish.
Further typing and page actions stay blocked while that result is checked.

## Verification and migration

```bash
python -m pytest tests/test_general_assistant.py tests/test_manifest_contracts.py -q
```

Tests exercise compiled bindings, native IPC contracts, human help, memory
isolation, action fencing and output privacy using deterministic models and
helper responses. A native source build verifies the Swift app without opening
it. Live OS grants, default-provider vision and website acceptance are separate
opt-in checks; tests do not send real email.
Explicit fake-model or fake-skill execution rejects live computer control before
opening the helper. Conversation-only tests can still discuss its capabilities.

REST `RunCreate.inputs` uses the compiled entry-point shape:
`{"prepare_task__start":[{"args":[],"kwargs":{"task":"...","target_app_bundle_id":"com.google.Chrome"}}]}`.
The app scope keeps input in the requested app and the per-run task leaves saved
setup instructions unchanged.

Version 3 replaces the previous file/Harness2/OpenShell product. Refresh prepared
Jobs and review saved instructions before running. Old input-folder and harness
settings are not migrated or executed; existing historical runs remain historical.
