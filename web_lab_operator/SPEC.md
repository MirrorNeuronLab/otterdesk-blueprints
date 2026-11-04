# Web Lab Operator specification

## Outcome

A supervisor supplies Markdown describing a simulated web lab's purpose and
numbered procedure. A model produces a typed, source-linked plan. The co-worker
executes supported steps through PyLabRobot Chatterbox, observes tip and liquid
trackers, makes bounded next-step decisions and publishes evidence and a replay.
This is simulation for protocol development and teaching, not a physical lab.

## Experience memory

Version 1.1 enables the existing `mn.context.text.v1` profile and SDK `context`
extra. Authenticated Membrane v2 retains job-private runtime-authored Markdown,
not a blueprint-owned database. The web lab principal can recall only authorized
records in its trusted Job scope. Knowledge RAG remains separate.

Commit each observed step checkpoint before publishing its memory record.
Retain the fixed step, actual chosen source, affected well states, tips, outcome,
timestamp, run/procedure/plan identities, policy revision and artifact provenance.
Distinguish passed, failed, paused and rejected outcomes; model reasons remain
qualified proposals. Record run completion, unmet goals and selected review
issues against complete evidence. Cleanup attempts to remember interruptions;
if memory is unavailable, retain the original failure and a memory diagnostic.

Planning recalls prior matching procedure outcomes plus recent Job run summaries
to help review a revised procedure. Per-step recall filters exact procedure and
step identities and includes recent current-run observations. Typed analytical
queries reserve results for successes and failures. Native hydration verifies
canonical Markdown revisions. Use whole records within configured bounds,
expose omissions, and keep full witnesses/citations outside the model packet.
Current input and tracker state always control execution. Memory cannot expand
the allowed action language, source candidates or hardware boundary.

Freeze every retrieval packet before the associated model request. Replay uses
the same packet, original event timestamp and immutable outcome identity; it
cannot learn an action twice or rewrite an earlier decision using future history.
An enabled memory failure is an observable phase failure. The standard explicit
disabled override makes no context calls and preserves the simulation policy.
Publish required `memory.json` with supplied context and native receipts, and
report the enabled/disabled state. Defaults are six records and 18,000 bytes;
the result limit is configurable within 3..12 and does not imply exhaustive recall.

## Inputs and procedure language

Accept exactly one UTF-8 Markdown text or staged `.md` file, at most 32,000 bytes.
The bundled procedure is `examples/sample_inputs/procedure.md`, accompanied by a
sample README and `otterdesk.sample_dataset.v1` inventory. Defaults, setup sample,
demo configuration and task inputs select that same SDK `@/` bundle reference.
Require explicit inventory, one to four named 96-well 360 uL plates, numbered
steps and observable final volume goals. One channel and 96 fresh 300 uL tips
are fixed. Unlisted wells begin empty. Operations are transfer (0.1..360 uL),
mix (0.1..300 uL, 1..10 cycles), wait (0..30 virtual seconds) and volume check.
Intake annotates numbered instructions with their exact text and physical source
line numbers, using the same parser as plan coverage validation. The model copies
those references instead of counting lines. Original Markdown bytes remain the
authoritative artifact. Each step points to source Markdown lines. All numbered
instructions must be
represented. Missing parameters, unsupported operations or assumptions require
review and admit no simulation actions. No code from Markdown is executed.

## Adaptation and observation

Before every step the model receives current tracked volumes and tips, the
fixed step, allowed source candidates and previous outcome. A decision is
execute, adapt or pause. Only a transfer source can change, only to a source
explicitly declared in the plan for that transfer, only when the primary is
short, and only to one holding enough of the same nominal liquid. No change to
amounts, destination, step order or goals is permitted. Deterministic policy
validates every decision before command dispatch. Transfers above tip capacity
split into <=300 uL chunks with fresh tips. Invalid decisions, volume failures
and insufficient tips end the bounded procedure as Needs review.

Planning retains the requested primary source and declared alternates. A primary
shortage alone does not require review when one allowed same-liquid alternate
can supply the complete transfer. "Use the alternate instead" means the entire
amount comes from that alternate, without combining sources. Source selection
remains an execution-time decision against observed state.

No successful step is inferred from a model statement. The executor reads
PyLabRobot tracker state after operations. Completion requires every planned
step and every declared final volume goal to pass. Goals have at most 5 uL
tolerance. Model failures, timeouts, cancellation, required UI failures and
artifact-integrity failures remain observable failures; they are not replaced
with deterministic production success.

## Composition and lifecycle

Four logical steps compose existing SDK blocks. The shared structured-assessment
block owns initial model execution. The simulation hook uses the existing managed
model request journal and scoped checkpoints for its domain-specific procedure
loop. It owns no message routing, ACK/retry logic or Core completion protocol.
The existing Web UI binding and claim contract carries a single HTTP/WebSocket
listener serving the native PyLabRobot visualizer and bounded monitor state.
Intake and planning publish the native empty deck before reading inputs or
calling the model. No wells, volumes or remaining tip count are projected until
the validated plan reaches simulation. Each phase owns one generation of the
required listener, closed on success, failure, partial startup or cancellation.
Completed block replay does not start a listener. The simulation generation
replaces the planning view even when its port is reused. Core owns execution controls.

At most 80 steps execute inside the 900-second phase budget, also bounded by the
block deadline. Checks occur between simulator calls and animation ticks. Each
model request has a maximum 60-second transport timeout and zero retries. A
cancelled or timed-out model outcome is not redispatched without reconciliation.
A resumed attempt starts a fresh Chatterbox simulation, reconstructs confirmed
steps and verifies restored observations before advancing. A partly failed
command cannot resume. No replay can target a physical backend.

## Evidence and presentation

Preserve procedure bytes/hash, typed plan, initial inventory, source lines,
decisions/reasons, pre/post states, check outcomes, final goals and limitations.
Required artifacts are procedure, plan, trace, simulation, Markdown report and
JSON review results and the memory audit. Optional static replay/UI publication cannot block required
results. The replay provides all recorded states without a running service;
it is an observed-state replay, not the live PyLabRobot canvas. No confidential
input or unrestricted file-serving endpoint is exposed by the live page.

## Limits and acceptance

Model interpretation can be wrong despite source-line coverage. Liquid labels
are supplied metadata. No physical sensing, fluid dynamics, reaction kinetics,
contamination prediction, collision validation, assay result, medical judgment
or experimental validation is claimed. No hardware backend, arbitrary network
target, generated Python, package installation at run time or external upload
is available to the planner.

Acceptance includes canonical manifest compilation, actual stock-handler
execution with injected model responses, real Chatterbox tracker transfers and
mixing, source-shortage adaptation, undeclared/wrong-liquid source rejection,
overfill/tip exhaustion/failed-goal review, complete instruction coverage,
immutable replay, tamper detection, cancelled cleanup, optional presentation
failure isolation and narrow/wide replay layouts. Live provider, Docker image,
cross-node proxy and Core lifecycle behavior require separate live qualification.
Memory acceptance includes cross-run success/failure composition at actual
compiled model boundaries, revised-procedure qualification, job isolation,
whole-record omissions, no duplicate publication on replay, frozen context on
resume, explicit disable, memory outages and audit tamper detection. Injected
transports do not establish live Membrane storage or service behavior.
