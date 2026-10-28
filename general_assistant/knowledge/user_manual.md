# General Assistant user manual

## Getting started and reviewing work

I turn an agreed task and files you choose into deliverables you can review. The default task is a summary; you can give me writing, analysis or software work instead.

Choose an Input folder, an Output folder outside it, and Instructions describing the result you want. Input is read-only. A useful brief is: ‘Summarize these files, group the main topics, and list questions I need to resolve.’ Confirm the selected folders before starting; Downloads is the default, not a sample dataset.

Expect a saved answer and generated files under deliverables/ in the delivered run folder. The default task should create deliverables/summary.md. Actual tests, unresolved questions and missing tools belong in the handoff; generated code needs review before you use it.

Start with answer.md and the requested deliverable. Compare it with the brief, check which sources and checks support it, and identify anything unfinished. A successful run or private improvement cycle does not establish correctness. A missing check should be named, not counted as passed.

See [the conversation guide](conversation_guide.md) for the sample or walkthrough, expected handoff and useful follow-up questions. Examples are not current findings. Ask one missing question at a time, keep confirmed answers, and answer side questions without changing settings or issuing actions.

Speak directly about the agreed task and observed work. At setup, keep confirmed
answers and ask only for the next missing answer; an explanation does not start
work. While working, mention only useful findings, actual decisions or completion.
During review, use the selected run's saved answer, checks and limitations.
Treat previous runs as historical and state when current evidence is unavailable.

OtterDesk's Chat > Memory holds explicit supervisor preferences and working rules.
“Remember…” can save a rule for future runs; ordinary corrections apply to the
current dialogue. Inspect, change or forget saved instructions in Memory.
The next run captures the current list; changes never rewrite an active run.
These instructions grant no permissions. Private Harness2 lessons are not Chat
evidence; the public answer is available through prepared Membrane sources.

Setup asks for an input folder, an output folder and instructions. Input defaults
to `~/Downloads`; the default instructions summarize its contents into `summary.md`.
Input is read-only material, including Markdown, documents and source code.
Results go into `~/Documents/general-assistant` by default. Choose an output
location outside input.

Confirm the settings and start a run to create the summary. Change Instructions
for another task, for example: “Convert the Java code in the input folder to Rust.
Create a Cargo project in output and run its
tests. Report checks you could not perform.” Saved instructions apply to each
run unless a per-run task overrides them. If no instructions are configured,
answer the task request in Chat. Markdown input is supporting material, not
permission to replace the task or change the filesystem boundary.

Harness2 posts work and refinement notices in this conversation. If missing
information or a decision blocks work, it asks here, waits for your actual reply,
and continues the same work area. Reply within ten minutes. Each rollout allows
up to three clarification replies. Expired or cancelled requests cannot resume
work. OtterDesk's existing conversation interaction stream carries these
requests and replies. Standard Job MCP tools retain run supervision; no
additional Harness2 endpoint is needed. Capability and status
questions alone do not start work. Use start_run only when the human requests
work; use pause_run, resume_run and stop_run for the corresponding controls.

Read answer.md for results, evidence, checks and limitations. The configured
output folder contains run_<timestamp>/ with answer.md, result.json,
harness-audit.json and generated deliverables/, including summary.md for the
default task. Review converted code before applying it. Input is never edited
in place; builds and generated source stay in
output. Missing tools or package access must be reported, not presented as a
successful test.

The co-worker requires 32 GB system RAM, a tool-capable runtime default model,
and OpenShell on Linux with Landlock ABI 4+. Deployment administrators configure
the gateway and Core conversation connection. User setup has no model, gateway
or refinement settings.

Harness2 retains private prompts, lessons and helper scripts for this hired Job.
Failed tasks preserve previous memory. Model weights and sandbox policy never
change. Completing work or adopting a harness does not prove correctness or
quality improvement. Private memory and runtime caches are not exported.

Default network access permits the model gateway, the trusted conversation
controller and declared GitHub reads. Other tools and downloads require a
deployment policy change. Messages, purchases, deployments and external
mutations are outside scope.
