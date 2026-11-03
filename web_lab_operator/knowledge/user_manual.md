# Web Lab Operator manual

Web Lab Operator turns Markdown procedures into a simulation-only PyLabRobot
run. Supply exact starting plate/well volumes and liquid labels, numbered
transfer/mix/wait/check instructions and final well-volume goals. Use one to four
96-well plates and fresh 300 uL tips. The included synthetic example shows how
a declared reserve source can resolve an insufficient primary source.

Provide pasted Markdown or a .md file, clearing the other input. Start a run
explicitly. Open Web lab while it is running to see the native PyLabRobot deck
and recorded decisions. Use the co-worker's existing controls to pause, resume
or stop. Chat questions read context; they do not start work or edit a procedure.

Inspect plan.json, procedure.md, trace.json, simulation.json, memory.json and report.md.
After completion, the web result is an optional read-only deck replay with
observation controls. Needs review means the procedure stopped without proving
all required outcomes; revise the Markdown and start a new run. A missing or
unsupported instruction, unavailable liquid, exhausted tips or failed volume
check never counts as a completed experiment.

Membrane remembers observed step outcomes and run reviews within this hired
co-worker's private Job. Planning can consider prior successes, failures and
review issues; each next-step decision receives matching experience and recent
current-run observations. Current instructions and tracked state take precedence.
Earlier success cannot authorize another source, change a goal or skip a check.
Recall is bounded and may omit records. memory.json shows the history supplied,
its source citations, omissions and saved outcome receipts. A separate hired
co-worker has separate history. Memory is enabled by default; an unavailable
memory service stops the phase. An explicit text_memory.enabled=false override
disables recall and recording and marks the audit accordingly.

The standard supervision tools expose capabilities, run state, results and
execution controls. The blueprint adds no domain mutation tools. Saved
explanation preferences affect Chat wording only. See the
[conversation guide](conversation_guide.md) for stage-specific help.

No physical devices are available. Tracked volume is bookkeeping, not a liquid
measurement. Chemistry, incubation, contamination, collisions and biological
outcomes are outside this simulation. The selected model route receives the
procedure, bounded deck state and selected history. Runtime Membrane retains
job-private simulated experience; evidence remains in the runtime-owned run store.
