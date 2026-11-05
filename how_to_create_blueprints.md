# How to create an OtterDesk blueprint

Use one folder per co-worker. The folder and manifest own its mission, inputs, domain decisions and deliverables. MirrorNeuron prepares the Job, starts an admitted Run, executes its steps and publishes their results. Begin with a published package whose work resembles yours. VC Assistant is a batch example with several specialists. ROS AMR Controller is a supervised Compose service.

Start with a runnable empty blueprint:

```bash
./scripts/create_blueprint.sh -n my_blueprint
```

This creates and pushes the public
`MirrorNeuronLab/mn-blueprint-my_blueprint` repository, then stages its pinned
submodule in this catalog. It includes an MIT license, a canonical package,
standard supervision, an empty domain hook and an offline test. The workflow
does no domain work or model inference. The parent is not committed and
`index.json` is unchanged. The command requires Git, Python 3.9+, authenticated
`gh`, organization repository-creation permission and SSH push access.
The generated blueprint runs with the normal Python 3.12 MirrorNeuron runtime.

## Define the package

1. Write the product contract in the package’s `SPEC.md`. Name the input, the evidence the supervisor will see, any decisions that require approval, and what counts as completion or readiness.
2. Create a v1 `manifest.json` with a unique ID, name, version, and the role files `workflow.json`, `execution.json`, `contracts.json`, `dependencies.json` and `config/default.json`. Set `"payload_api": "mn.blueprint.v1"`. Add the required product, setup, conversation and other extension files for the chosen experience. Record only operator-tunable defaults in config.
3. Declare required inputs, types, linked config fields, output paths and optional artifacts in the contracts. Use `@/examples/sample_inputs` for a bundled sample and include that sample. Declare skills, agents and SDK components in dependencies. A stock block needs the `mn-blueprint-blocks` distribution. Use matching SDK builds with the v1 payload API on the controller and execution nodes. The catalog requires `mirrorneuron-python-sdk>=1.4.1.dev46,<2` for released packages.
4. The creation script sets up the public repository and pinned submodule.
   Add the folder ID to `index.json` when the implemented co-worker is ready
   for catalog publication. Keep its README, setup guide and tests aligned
   with the actual inputs and output receipts. Commit and push the package
   before updating the catalog pin;
   `./scripts/git-push-all.sh "Commit message"` publishes every changed package
   and then the catalog. Ordinary folders remain valid for local authoring.

## Compose the work

Use the `mn.blocks` extension for a stock logical step, service, event consumer or controlled operation. Set its `uses` version, inputs, hooks and limits. For a step that needs multiple specialists, keep its input, output and internal graph in `payloads/steps/` using `mn_sdk.blueprint.steps`. Use workflow `needs` for dependencies between logical steps.

In `execution.json`, a specialist can bind directly to a stock block. For example, this member of `agents.registry` binds one domain function.

```json
"company_packet_grouper": {
  "role": "Company packet grouper",
  "block": {
    "uses": "mn.blocks.domain_operation@1",
    "hooks": {
      "operation": "domain.intake_blocks:company_packet_grouper"
    },
    "limits": { "max_calls": 8, "timeout_seconds": 900 }
  }
}
```

Use the same `block` object in a child template’s `run`, or in an explicit Python executor node’s `config`. The compiler selects the worker entry point, binds the revision and checks the declared component. The workflow engine creates the step boundaries, routes messages, tracks attempts, and decides when the step completes. The hook owns a domain result.

## Select the runner

Worker groups can select a platform worker with their existing `uses` declaration. For an explicit executor, set `config.runner`. In a default worker, worker group, or per-step worker override, the same choice belongs under `with.runner`. If the stock Python worker needs a specific interpreter inside its image, set `with.python_executable`. The compiler supplies the module and invocation arguments.

| Runner | What the blueprint supplies |
| --- | --- |
| `host_local` | A native worker, its declared Python environment and any host requirements. |
| `docker_worker` | A worker image or build context and the command or Python block that runs inside the container. |
| `openshell` | An image or build context and a scoped sandbox policy for the required executables and destinations. |
| `docker_compose` | A payload-relative Compose context, its file, services and readiness checks. See `ros_amr_controller/execution.json` for a complete example. |

Keep the platform lifecycle out of Python hooks. Start, pause, resume and stop go through the Job and Run controls used by the desktop and `mn`. An adapter prepares or stops only resources owned by the corresponding definition or Run. For a service, wait for its serving receipt before treating it as ready. For a batch, wait for the terminal Run and verify the required artifacts.

For a long-running Compose service, declare the Job as a service. A pause can return `pause_pending` while its containers shut down. Wait for the `job_paused` event before resuming. An explicit resume starts another serving generation after the runtime confirms the stop. Ordinary domain actions with an uncertain outcome keep their review requirement.

Declare required ports, storage, GPU and placement in the appropriate execution resources and policies. Compose and model work in the same admitted Run reuse its Job allocation. An auxiliary service should declare its own readiness and stop behavior only when it is required for the product.

## Implement domain hooks

Keep implementation under `payloads/domain/` in small modules named for the work. A stock block supplies its context when it calls the hook. Use named imports from `mn_sdk.blueprint` capability modules. Compilation checks authored SDK imports against the v1 export list before loading step code.

| Task | Public entry point |
| --- | --- |
| Capture declared inputs | `mn_sdk.blueprint.inputs.capture_declared_inputs`, with the hook context, request and `runtime_file=__file__`. The helper resolves staged paths and saves the input receipt. |
| Define step ports and collaboration | `mn_sdk.blueprint.steps` provides `StepSpec`, `InputSpec`, `OutputSpec`, `agent`, `sequence` and `parallel`. |
| Execute domain work | `mn_sdk.blueprint.hooks` provides the block context type, capability, activity and budget primitives. Use the context’s cancellation checks, idempotent checkpoints and artifact store. |
| Read evidence or call a declared model | `mn_sdk.blueprint.knowledge`, `memory` and `models` expose scoped capabilities. Declare the component and its requirements first. |
| Publish results | `mn_sdk.blueprint.outputs` provides file capture, frozen publication and verified artifact delivery. Store large or private content before returning a bounded reference. |
| Request a decision or supervise a service | Use `mn_sdk.blueprint.approvals` and `services`. Job and Run identities come from the runtime. |

Parallel workers that need one shared value, such as a snapshot’s publication
time, can call `ContextSession.get_or_create_checkpoint(key, value)`. Each
worker receives the same committed value. Keep effect and evidence receipts
scoped to the block invocation so a retry can recover completed work.

For a service that updates a JSON status on each cycle, declare the primary output as a `service_result` with a path and schema version. Create `mn_sdk.blueprint.services.service_status_publisher(runtime)` once from the SDK-provided run context and call it with each new status. The SDK writes the same snapshot to the run store and the configured output destination.

For a live page, declare the Web UI companion and bind the listener with
`resolve_web_ui_binding`. Register `binding.advertised_url(port)` after the
listener starts so the proxy uses the address assigned by the runner.

Use the public APIs of any declared companion component, skill or agent for its own domain. To import an SDK companion such as `mn_sdk_web_ui`, list its distribution (`mn-python-sdk-web-ui`) in `dependencies.json`. The compiler rejects undeclared SDK companions, private companion imports, and platform CLI or API imports. The CLI client, native-resource registry, submission pipeline, runner commands and worker environment variables belong to MirrorNeuron. A new reusable capability belongs in its owning SDK component or skill, with a contract test, before a blueprint imports it.

## Verify the package

Exercise the authoring and execution boundaries separately. Run the catalog compiler tests against the published inventory.

```bash
python -m pytest -q tests/test_catalog_native_blocks.py tests/test_sdk_package_contracts.py
```

Run the co-worker with its declared sample from the catalog root.

```bash
mn blueprint run ./vc_assistant --fake-llm --fake-skills --detached --follow-seconds 0 --json
mn run show <run-id>
mn run logs <run-id> --channel events
```

Check the final receipt and required files for a batch. Exercise pause, resume and cancellation for a supervised service, including an independent Job that stays healthy during cleanup. Fake models and skills still exercise placement, runner preparation, admission and lifecycle. The target node must satisfy the real hardware, image and sandbox requirements. Reprepare the test Job after changing its definition or SDK code. Previously submitted Jobs retain their compiled bindings and component identities.

The cookbook for shared blocks is in [SHARED_BLOCKS.md](SHARED_BLOCKS.md). Graph examples are in [DAG_FLOW_PATTERNS.md](DAG_FLOW_PATTERNS.md). The [catalog E2E guide](tests/e2e/README.md) describes the live fixtures, prerequisites and evidence.
