# Web Lab Operator

Turn a Markdown lab procedure into a supervised **PyLabRobot simulation**. The
co-worker plans typed steps, observes the tracked deck before each step and can
switch to an explicitly allowed source well when the primary source is short.
Watch the native PyLabRobot visualizer during the run; review a self-contained
deck replay, decisions and final volume checks afterwards. Membrane retains
job-private experience so later decisions can consider what worked and failed.

This blueprint controls simulated liquid handling only. It never constructs a
hardware backend or executes model-generated Python. PyLabRobot's trackers model
liquid volumes and tips; they do not establish experimental or physical results.

## Start with the included example

Prepare a MirrorNeuron Docker worker, the runtime's configured text model and
its matching authenticated Membrane v2 context service,
then hire **Web Lab Operator** in OtterDesk and select the included sample. From
a checkout you can also run:

```bash
mn blueprint run ./web_lab_operator
```

For your own file:

```bash
mn blueprint run ./web_lab_operator --set inputs.payload.procedure_file=/absolute/path/procedure.md
```

The synthetic Markdown example requests a 100 uL transfer from a well holding
20 uL, explicitly permits a reserve holding 200 uL, then mixes, waits and checks
the result. A successful adaptive run leaves the primary well at 20 uL, reserve
at 100 uL and destination at 100 uL, with 94 unused tips. Model interpretation
and decisions remain live; there is no production fake-model success path.

Open **Web lab** as soon as the run starts. The native deck is empty during
intake and planning. Once the plan is validated, the simulation worker supplies
the plates, starting volumes and live tip state. Each phase owns its listener
and closes it on completion, cancellation or failure. The desktop follows the
new page automatically, including in a detached window. The
optional saved replay then becomes the run's web result. Use the existing
co-worker controls to pause, resume or stop; asking a question never starts work.

## Write a procedure

Provide either `inputs.payload.procedure_markdown` or
`inputs.payload.procedure_file`, and clear the other value. Text and files are
bounded to 32,000 UTF-8 bytes. Files use `.md` and are staged by the runtime.
The default file is
[`examples/sample_inputs/procedure.md`](examples/sample_inputs/procedure.md).
The sample folder includes its README and `SAMPLE_DATASET_MANIFEST.json` inventory.
`examples/task.json` contains run inputs; `examples/demo.json` is a configuration
overlay selecting the same sample. Expected model responses are test fixtures
under `tests/fixtures/web_lab_operator/`, outside the published package.

Include:

1. The purpose and names of one to four 96-well plates (360 uL per well).
2. A starting inventory with exact plate/well, liquid label and volume in uL.
   All unlisted wells are empty. A single rack supplies 96 fresh 300 uL tips.
3. Numbered instructions using transfer, mix, wait or volume check.
4. Explicit final well-volume goals and tolerances (0..5 uL).
5. Any allowed alternate source for each transfer. It must have the same
   nominal liquid identity and hold the full requested amount by itself.

The plan retains the primary source and allowed reserves. A short primary source
can still produce a ready plan when an allowed reserve holds the full transfer.
The simulator selects the reserve after observing the deck, takes the complete
amount from it and leaves the short primary unchanged.

Transfers are bounded to 360 uL and split into chunks of at most 300 uL. Each
chunk uses a fresh tip. Mixing uses one fresh tip, at most 300 uL and 1..10 cycles.
Waits advance virtual time by 0..30 seconds; they do not simulate reactions.
There are at most 80 steps and a 900-second simulation-phase deadline.
`simulation.max_steps`, `simulation.max_duration_seconds` and
`simulation.action_delay_seconds` can reduce those bounds or change animation
pacing. They cannot enable physical operation or an unsupported instrument.

The model must mark assumptions or unsupported instructions **Needs review**.
Every numbered source instruction must be represented in a ready plan. Intake
supplies exact physical line references for those instructions; the coverage
validator uses the same parser. Before each action, deterministic policy checks
deck resources, available tips, source
volume, destination capacity and the adaptation envelope. It cannot revise the
goal, transfer amount, destination or step order. A failed check, missing source,
unsafe decision or exhausted inventory ends the procedure with review evidence.
Revise the Markdown and start a new run to correct it.

## Remember prior work

Memory is enabled by default. After each confirmed step, the co-worker saves
its action, affected wells before and after, tip count, outcome and source
references as authored Markdown through the SDK's Membrane TextMemory API.
Successful adaptations, failed checks, rejected choices and pauses stay
distinct. The final run record includes completion and unmet goals. Interrupted
runs also attempt to save a qualified failure or cancellation record; a memory
failure during cleanup is recorded in `memory-interruption-error.json` while
the original runtime failure remains visible.

Before planning, recall includes earlier outcomes for this exact procedure and
recent run summaries from the same hired co-worker. A revised procedure can see
earlier review issues without inheriting their inventory or instructions.
Before every simulated step, recall selects matching procedure/step identities
and recent observations from the current run, reserving space for both successes
and failures. This history is supplied to the model to inform its next decision;
it does not change model weights. The current Markdown, observed deck and
deterministic execution policy remain authoritative. Historical text cannot add
sources, bypass a check or authorize hardware.

Memory is private to the stable runtime Job and the web lab principal. Repeated
runs of that hired co-worker share it; another hired Job has separate memory.
Records include run, procedure and policy provenance. The runtime owns durable
Markdown and DuckDB storage, authentication and service preparation. Reference
knowledge RAG remains separate. No runtime changes or blueprint-owned memory
database are needed.

`text_memory.max_results` defaults to 6 (supported 3..12), with an 18,000-byte
`text_memory.max_context_bytes` share. Retrieval is bounded, not exhaustive;
oversized records are omitted whole and omissions are visible in `memory.json`.
Selection is frozen before model dispatch, so resume cannot replace a decision's
original history with its own later outcomes. SDK checkpoints and immutable
Membrane records prevent duplicate learning on replay. When enabled, unavailable
memory stops the phase; it does not silently run without history. An explicit
`text_memory.enabled=false` override disables reads, writes and service
preparation and marks the saved audit as disabled.

## Inspect the evidence

| Artifact | Contents |
| --- | --- |
| `procedure.md` | Exact supplied Markdown and its SHA-256 identity in the result |
| `plan.json` | Typed plan, initial inventory, instruction-line references and unresolved items |
| `trace.json` | Initial state, each decision, pre/post observations and outcomes |
| `simulation.json` | Final tracked state and volume goals |
| `memory.json` | History supplied to each model decision, source citations, query witnesses and saved outcome receipts |
| `report.md`, `final_artifact.json`, `result.json` | Review outcome and qualifications |
| `web/index.html`, `web_ui.json` | Optional standalone replay and static Web UI handle |
| `interrupted-simulation.json` | Qualified observed state when a phase is interrupted |

The runtime owns output delivery to `~/Downloads/web-lab-operator/run_<timestamp>/`.
Large results stay in committed artifacts rather than coordination messages.
Required report publication failures remain failures; optional replay-rendering
failure cannot invalidate an already recorded simulation or required report.

## Runtime composition and privacy

`capture_lab_procedure` → `plan_lab_procedure` → `simulate_lab_procedure` →
`publish_lab_review` uses stock `domain_operation` and `structured_assessment`
blocks. SDK input capture, managed model journals, checkpoints, publication and
Web UI claims and Membrane persistence retain their existing owners. Intake and
planning require the blocks package with paired batch resource hooks; use a
desktop build that follows changes to the runtime UI claim. Domain policy, the
PyLabRobot integration and selected presentation live under `payloads/domain/`.

The Python 3.12 Docker image installs pinned PyLabRobot and WebSocket versions.
Its build downloads hash-checked visualizer dependencies and serves them locally;
the browser does not use CDNs. Planning and adaptive decisions send the procedure
and selected simulation state and recalled experience to the configured model route.
Selected simulation experience persists in the authenticated job-private Membrane service.
No robot address,
serial/USB device, arbitrary tool, shell or generated-code endpoint is exposed.
The standard runtime Web UI proxy owns authentication and cross-node transport.

Completed step checkpoints are immutable. A replacement attempt reconstructs a
fresh simulator from confirmed actions and compares each restored observation.
SDK model receipts prevent repeat billing on ordinary replay; an uncertain model
outcome remains fenced. A partly failed simulated command requires a new run.

## Validate

With the repository's sibling SDK/agent/skill sources and Python test dependencies:

```bash
python -m pytest tests/test_web_lab_operator.py -q
python -m pytest tests/test_membrane_catalog.py tests/test_sdk_package_contracts.py -q -k web_lab_operator
python -m pytest tests/test_manifest_contracts.py -q
python -m pytest tests -q
git diff --check
```

Unit and compiled-handler tests inject deterministic model responses and never
contact a provider. PyLabRobot tracker tests use its real Chatterbox backend.
Live model, Docker build, cross-node UI proxy and Core pause/resume acceptance
are separate opt-in checks; offline tests do not qualify those integrations.

Reference: [PyLabRobot](https://github.com/PyLabRobot/pylabrobot) and its
[Visualizer guide](https://docs.pylabrobot.org/stable/user_guide/machine-agnostic-features/using-the-visualizer.html).
