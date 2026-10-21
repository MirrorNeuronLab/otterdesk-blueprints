# Procurement Manager implementation map

The published catalog path is `procurement_manager/`; the installed blueprint ID remains `procurement_manager` so existing hired jobs and artifact identities continue to resolve. `index.json` is the catalog inventory, `manifest.json` owns display identity, `workflow.json` owns logical steps, `execution.json` owns worker bindings, and `contracts.json` owns input and output contracts.

The deployed workflow has six logical steps. Five declare SDK domain-operation
blocks; `compare_purchase_options` retains its market/cost/risk StepSpec graph.
The seven specialists bind directly to native functions in `intake.py`,
`comparison.py` and `reporting.py`. Immutable purchase snapshots remain separate
from `procurement_case_packet.json`; publication
verifies the joined case summary and packet before rendering. The former local
composition runner is removed. Offline samples execute the compiled workers and
field mappings through `tests/block_workflow_fixture.py`; Core owns scheduling.

The existing platform patterns are in `/Users/homer/Projects/mn-blueprints`: `demo_dag_conditional_branch` for selected branches, `demo_dag_scatter_gather` for supplier fan-out, `demo_dag_quorum` for quote quorum, `demo_dynamic_workflow` for admitted bounded graph patches, `demo_human_approval` for Core human control, and `demo_checkpoint_replay` for replay recovery. `mn_sdk.step_graph` already provides `parallel`, `choice`, and `bounded_loop` for internal agent collaboration. The procurement implementation should compose these contracts through the SDK and Core; it must not add a blueprint-owned scheduler.

OtterDesk reads blueprint identity and setup from the manifest and `extensions/ui.json`. First-run setup and sample actions are implemented in `src/main/services/worker-setup.js` and `src/renderer/src/features/workers/pages/WorkerChatPage.tsx` in the desktop repository. The renderer already has a workflow monitor and topology projection under `src/renderer/src/features/workers/lib/`. The UI should consume persisted Core state and bounded case artifacts instead of computing procurement status from chat text.

`payloads/domain/procurement_cost.py` contains decimal cash-flow calculations for the new quote contract. `examples/procurement_case/procurement_case.json` is a synthetic fixture with a simulated clock, immediate and delayed quote availability, and a no-response deadline. Advancing the fixture clock models supplier waits without sleeping or contacting suppliers. `assess_procurement_case` branches after evidence preparation and joins the existing recommendation audit at publication. Its assessor reads one selected case document and writes a bounded case packet independently of the legacy comparison state. The current branch provides a read-only comparison and emits exact-digest review requests through the existing run human-event contract, which OtterDesk displays as conversation actions. Responses are recorded there. The branch does not yet apply those responses to case progression, draft handoff, or mock ordering.
