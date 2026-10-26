# General Assistant specification

## Product contract

Version 2.1.0 has three setup fields: input folder, output folder and instructions.
Input defaults to `~/Downloads`; instructions default to summarizing its contents
into `summary.md` in output. Output defaults to `~/Documents/general-assistant`
so generated files remain outside the read-only input folder. Input is required,
readable task material, including Markdown and source code. Instructions are
saved configuration and may be overridden by an explicit per-run task. If absent,
admission requests a task through the standard human-interaction channel.
Subsequent clarification questions and human decisions remain in Chat.

The co-worker handles general writing, analysis, planning, document and software
tasks. For Java-to-Rust conversion, it reads Java input and creates the Rust
project and checks in output, preserving the input. Generated results use the
standard per-run output folder. Source-diff export is removed in this major
version; no migration of previous private harness prompts is implied.

Admission requires 32 GB system RAM independent of GPU type. Every Harness2 role
uses the prepared runtime `default` model route. Model serving and placement
remain platform responsibilities.

## Composition

Three serial native domain-operation blocks own admission, encapsulated execution
and publication. Only execution uses OpenShell. Harness2 is an unmodified,
commit-pinned dependency in the worker image. Its BenchmarkAdapter, Proposer,
Library and run_task APIs retain upstream recursion, selection and reflection.
There is no benchmark inventory or parallel blueprint-owned workflow runner.

SDK/Core own input staging, nested artifact-reference transport and output-folder
delivery. The owner passes immutable input and private memory snapshots, then
receives committed artifacts and an updated opaque memory snapshot. Owner
storage is never mounted writable in OpenShell.

## Input and output boundary

Each solver rollout has immutable captured `input/` material and a writable
`output/` work area. Every model subprocess uses the shared OpenCode skill's
Linux Landlock scopes; descendants inherit them. Writes, truncation, creates,
deletes, links and renames cannot alter input contents or paths. Build products
and generated source belong in output. A separate writable private runtime
folder contains CLI caches and temporary state, never user deliverables.
Improvers may write their private `context/harness` tree, not source material.

Landlock ABI 4+ on Linux ARM64/x86-64 is required; unsupported enforcement fails
closed with no unrestricted fallback. Landlock does not mediate chmod/chown
metadata on disposable copies. Input content/path integrity is checked before
accepting results, and the original host input is never mounted in the worker.
Untrusted Markdown or other input instructions cannot change task authority.

The trusted controller's Core conversation RPC is separate from the model route.
Model processes cannot connect to its TCP port and do not inherit Core tokens.
The outer OpenShell policy continues to authorize binaries, hosts and HTTP routes.

## Conversation contract

Core remains the authority for human notices, questions and response receipts.
Missing task instructions use a blocking missing-information request. Solver
work/refinement and result-ready notifications use nonblocking notices. OtterDesk's existing
interaction subscription and reply controls present these in Chat. Standard Job
MCP tools retain lifecycle supervision; human replies use the Core interaction
contract. There is no new domain MCP tool or alternate conversation store.

A blocked solver returns `{"input_required":{"question":"..."}}` as its final
session response. The trusted controller publishes the bounded question, waits
for a real reply for the exact request/run and continues the same workspace with
that reply. Cancellation, expiry, foreign request IDs and empty answers reject
continuation. Three replies per rollout are allowed, each bounded to ten minutes
and the remaining overall allowance. Identical questions reuse the recorded
human reply across probes. Chat replies are bounded to Core's 8,000-byte limit;
direct per-run task inputs retain the 64,000-byte limit. This authorizes no
external side effects.

## Persistence, limits and failures

The Job-private harness_memory resource retains the active harness and lesson
library. Successful publication verifies artifact hashes and advances generation
once using compare-and-swap. Failed work preserves previous memory. Replay cannot
advance a generation twice; stale runs cannot overwrite newer context. Separate
Jobs remain isolated. Membrane TextMemory recall is disabled.

Defaults allow 64,000 UTF-8 task bytes; 512 input/output files and 32 MiB for each;
1,024 memory files and 8 MiB. Symlinks, path conflicts and quota overflow fail.
Sequential k=1 is the default; deployment config permits parallel mode and k=1–3.
All roles share 24 sessions / 7,200 seconds, with 600 seconds and 8 MiB captured
CLI output per session. Clarifications consume this allowance. There is no worker
retry after interrupted uncommitted execution; reconciliation is required.

Harness2 may adapt prompts, skills, scripts and memory, never model weights or
outer policy. Plugins and delegated subagents remain disabled. Refinement is not
a guarantee of monotonic quality. Missing compilers, dependencies or network
access are explicit limitations, not successful checks.

## Outputs and evaluation

Public results are result.json, answer.md, harness-audit.json and generated
files under deliverables/. The default task creates deliverables/summary.md.
Private memory, CLI state and raw session context are not exported. The SDK/Core
deliver declared outputs to the configured output
folder using standard run_<timestamp> layout.

Acceptance compiles the source package, verifies the three setup fields,
Downloads/summary defaults and 32 GB/default-model contracts, exercises both actual
Harness2 recursion modes with deterministic sessions, checks task entry and clarification continuation,
rejects foreign/expired replies, preserves Markdown and source, and verifies
private memory, replay, quotas and declared publication. Shared skill tests
exercise actual Linux write/rename/delete/truncation/hardlink/symlink/descendant
restrictions and TCP port isolation with fake executables. Live OpenShell,
model, authentication and desktop conversation acceptance are deployment checks.

## Limits and compatibility

Deploy matching OpenCode scope support before distributing the 2.x package.
The 2.1.0 defaults apply to newly configured co-workers; existing saved settings
are not rewritten. Per-run tasks and Core clarification replies remain compatible.
Internal gateway/Core addresses and recursion budgets remain deployment defaults,
not customer setup fields. Default egress is model, controller RPC and declared
GitHub reads. Input, task and private context may be visible to the configured
model provider. The co-worker cannot change original input, send messages, buy,
deploy, train weights or guarantee professional or software correctness.
