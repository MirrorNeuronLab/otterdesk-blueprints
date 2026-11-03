# Computer Use user manual

Give a task in plain language, including the app, intended result and any details
needed to act. For example: “Using Gmail, send an email to alex@example.com with
subject Lunch and body Can we meet tomorrow?” The co-worker uses a dedicated
native Mac helper as a headless tool service; Chat remains in OtterDesk.

Use macOS 14+ with at least 24 GB RAM and an unlocked local desktop. Your system's
default LLM provider supplies the catalog's logical vision model, with verified
image input and structured JSON output. The shared text-model default remains
unchanged. Adding this co-worker downloads and prepares the signed, notarized
mn computer use.app. Installing OtterDesk or the runtime does not install it.
When prompted, grant mn computer use Accessibility and Screen
Recording in System Settings. These grants belong to mn computer use, not OtterDesk.
Use the CU menu to stop control immediately. Keep the target window visible;
capture crops to its focused window across displays when available. Text is
bound to a named editable field, with focus checked by the native helper.

Instructions are optional at setup. If empty, the run asks for a task in Chat.
The output folder defaults to ~/Documents/computer-use. Start work only when the
human requests it; questions about capabilities do not start a run. Use standard
Job MCP start_run/pause_run/resume_run/stop_run for explicit lifecycle requests.

If an app needs opening, login, MFA, CAPTCHA, permissions or missing details,
the co-worker suspends control and asks in Chat. Do the requested step in the
app, then reply. It also asks for help after repeated inputs leave the screen
unchanged, or before repeated navigation opens the same page or app again.
New tabs alone do not count as progress. Never paste passwords or authentication
codes into Chat.
Replies expire after at most ten minutes. The co-worker checks the screen again;
your reply alone does not prove completion. Stop/cancel/foreign replies cannot
resume work. Screen text cannot authorize unrelated actions.

The result is answer.md, result.json and computer-use-audit.json in a delivered
run_<timestamp> folder. Start with the observed result and limitations. An input
receipt alone does not prove a website accepted a send. If an action has an
unknown outcome, inspect the desktop before starting another run; do not repeat
an email blindly. Historical results are not current findings.

Membrane remembers successful navigation privately for this hired Job. It can
reuse app navigation hints, but must observe the current screen and cannot
assume login state. Stored hints omit typed text, email content, credentials,
URL paths/queries, screenshots and coordinates. Separate visual memory uses
EmbeddingGemma 2 to encode screenshots of completed work and recall similar app
layouts. These private images can contain visible email or other screen content.
The default cap is 32 states and 64 MiB; new learning stops at capacity while
existing recall continues. Images and vectors are not exported with results.
Historical field hints are checked against current controls and never replay a
send or typed text. A memory failure after completion does not undo the result.
Explicit supervisor preferences
remain in Chat > Memory and apply to the next run. They grant no new authority.
Raw model screenshots remain private run artifacts; selected successful images
also remain in the Job's private visual memory.

See [the conversation guide](conversation_guide.md) for a safe walkthrough and
how to review the result. Examples describe possible tasks, not completed work.
