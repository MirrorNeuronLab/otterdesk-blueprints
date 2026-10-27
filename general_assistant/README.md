# General Assistant

By default, this co-worker summarizes `~/Downloads` into `summary.md`. It uses [Harness2](https://github.com/google-research/harness2)
to work with files in a read-only input folder and save generated work in a
separate output folder. Markdown files, documents and source code are readable
input. Harness2 refines its working approach and retains private lessons for
later tasks of the same hired co-worker; model weights stay fixed.

## Setup and use

Setup has three fields: **Input folder**, **Output folder** and **Instructions**.
Input defaults to `~/Downloads`. Instructions default to “Summarize the contents
of the input folder and save the summary as summary.md in the output folder.”
Output defaults to `~/Documents/general-assistant`, outside the input folder.
Choose separate folders. Input supplies read-only task material; edits, build
products and generated files belong in output.

Confirm the settings and start a run to create the summary. Change Instructions
to give the co-worker another task. For example:

> Convert the Java code in the input folder to Rust. Preserve behavior, create
> a Cargo project in the output folder, run its tests, and report anything you
> could not verify.

Saved instructions apply to each run unless a per-run task overrides them.
When no instructions are configured, the co-worker asks for a task in Chat.
Markdown within input is supporting material, not permission to start unrelated work or change
the filesystem boundary. The launcher can also supply a task as a run input:

```bash
mn blueprint run ./general_assistant \
  --set inputs.payload.input_folder=/absolute/path/to/java-project \
  --set outputs.folder_path=/absolute/path/to/rust-results \
  --set 'inputs.payload.task=Convert the Java code to Rust. Preserve behavior and verify the result.'
```

`examples/sample_inputs/` contains synthetic Java and Markdown material.
To try it with the default summary instructions, run on the PC that will execute
the OpenShell worker:

```bash
mn job create ./general_assistant --job-id general-assistant-demo \
  --config ./general_assistant/examples/demo.json
mn job start general-assistant-demo --queue
```

The expected generated file is `run_<timestamp>/deliverables/summary.md`, alongside
`answer.md`, `result.json` and `harness-audit.json`. Setup and launch overrides are
read from the runtime-resolved configuration, including the staged input folder;
compiled defaults must not replace them with paths from the launching PC.
The demo config changes only the two folders and keeps the general summary
instructions. For a connected PC, add its node ID from `mn node list` to
`mn job create` with `--node`.

Staging excludes `.git`, environments, dependency caches, `.aws`, `.ssh` and
`.env` files. Input symlinks and quota overflow fail explicitly. Select a
narrowly scoped folder; its included contents can be read by the configured model.

## Conversation and supervision

Task entry, Harness2 work/refinement notices, clarification questions and the
result-ready notice use the standard Core human-interaction authority. OtterDesk
presents them in the co-worker conversation through its existing interaction
subscription and reply controls. Standard Job MCP tools start, pause, resume and
stop runs; human replies use the existing Core interaction contract. There is no
separate Harness2 chat server or blueprint-specific MCP endpoint.

If a rollout needs a human decision, it returns a structured question to the
trusted controller. The controller publishes a blocking conversation request,
waits for the actual Core-authoritative reply, and continues the same workspace
with that reply. It never invents an answer or treats input-file instructions as
human approval. Each rollout permits up to three clarification replies, each
with at most ten minutes to respond and within the overall run allowance.
Expired, cancelled and mismatched replies cannot resume work. Standard pause,
resume and stop controls continue to apply. Capability/status questions alone
do not start work.

## Runtime and isolation

- At least **32 GB system RAM**, two CPU cores and 16 GB disk. No GPU vendor,
  VRAM or GPU count restriction; the runtime default model has its own serving
  requirements and must support tools.
- Standard MirrorNeuron OpenShell provisioning and artifact handoff v1. The
  Linux ARM64/x86-64 image uses Python 3.12 and Harness2 commit
  `1cfe254e8d25b15f37048c3730134686abe60335`.
- The shared OpenCode skill must include `writable_paths` and `connect_ports`
  support. Install matching local skill source or the declared updated package.
  Linux **Landlock ABI 4+** is required. Scope installation fails closed.

`prepare_task` receives the task and freezes input references and private memory.
`solve_task` runs actual Harness2 in OpenShell. Every rollout gets a fresh captured
`input/` tree and an `output/` work area. Linux restrictions prevent task processes
and descendants from changing input contents, creating/deleting/renaming input
files, or writing task files outside output. Private OpenCode cache/temp state is
separate and never exported. Input bytes and file names are also checked before
accepting a rollout. Landlock does not mediate chmod/chown metadata on disposable
copies; original host input is never mounted in the worker.

Improvement sessions may edit only their private harness tree. The trusted
controller reaches Core for conversation; model/tool subprocesses cannot connect
to that RPC port. SDK/Core own artifact transport and output-folder delivery.
`publish_task` verifies generated artifacts, adopts successful private memory and
publishes only declared results.

The default is one sequential Propose–Probe–Compose refinement step, involving
four solver rollouts plus improvement and reflection sessions. This uses more
model work than one direct answer. Internal deployment defaults allow 24 sessions,
two hours total and ten minutes per session. Parallel recursion and budgets are
deployment configuration, not setup fields. Each clarification consumes another
session. Identical questions reuse the recorded human reply across probes. Runtime plugins and delegated subagents are disabled.

Harness2 prompts, memory, skills, scripts and lesson library stay in the Job's
private `harness_memory` resource. Successful completion advances a checked memory
generation; failed work preserves the previous generation. Separate hired Jobs
never share this state. Membrane TextMemory recall remains disabled.

Deployment configuration uses `harness.gateway_host` / `gateway_port` (defaults:
`host.docker.internal:4000`) and `harness.core_port` (55051 on the same host).
Core must use a separate port from model/public HTTPS. The controller receives
runtime authentication through `MN_GRPC_AUTH_TOKEN` and model authentication
through `MN_LLM_API_KEY`; model subprocesses do not inherit the Core token.

## Outputs and limits

SDK/Core deliver `result.json`, `answer.md`, `harness-audit.json` and generated
`deliverables/` into `<output folder>/run_<timestamp>/`. Converted source is
created directly as a deliverable, rather than by editing input and exporting a
diff. The default task writes `deliverables/summary.md`. The audit records actual
sessions, available usage receipts, adopted harness and lesson counts. Private
memory, raw sessions and caches are excluded.
Failed rollouts include their bounded adapter error in the audit's
`rollout_failures`, including failures before the first model session.
A rollout must write a nonempty `output/answer.md` through its tools. A final
chat message alone does not count as a written result.

Default quotas are 512 files / 32 MiB for input and output, and 1,024 files / 8 MiB
for private memory. Symlinks, conflicting output names and quota overflow fail.
Completed checkpoints replay without model redispatch. Interrupted execution
without a committed result requires reconciliation.

The image has Python, Java, Rust/Cargo, build tools, Git, Pandoc and Poppler.
Other toolchains must be present in the selected deployment image to run their
checks; unavailable checks must be reported. Default network access permits model
calls, controller conversation RPC and declared GitHub GET/HEAD reads. Other
websites and package downloads require an explicit deployment policy change.
Messages, purchases, deployments and external mutations remain outside scope.
An artifact or refinement receipt does not independently prove task correctness.

## Verification

```bash
python -m pytest tests/test_general_assistant.py tests/test_manifest_contracts.py -q
```

Tests use the real pinned Harness2 engine with deterministic model sessions and
mocked Core interactions. The shared OpenCode tests separately exercise real
Linux write and TCP scopes with fake executables. Live model/OpenShell/Chat
acceptance remains an opt-in deployment check.
