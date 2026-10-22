# General Assistant user manual

Setup asks for only an input folder and an output folder. Input is read-only
material, including Markdown, documents and source code. Results go into the
separate output folder. Choose an output location outside input.

Start a run and answer the task request in Chat. For example: “Convert the Java
code in the input folder to Rust. Create a Cargo project in output and run its
tests. Report checks you could not perform.” The task applies to that run and is
not saved configuration. Markdown input is supporting material, not permission
to replace the task or change the filesystem boundary.

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
harness-audit.json and generated deliverables/. Review converted code before
applying it. Input is never edited in place; builds and generated source stay in
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
