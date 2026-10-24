# Microduck Controller

Version 5.1.1 removes an obsolete Docker copy of the empty `agents/` directory.
The service uses the SDK block worker and its `domain/` hooks; packaged builds
require only the declared runtime sources.

Microduck Controller packages the Microduck RL playground as a live OtterDesk service. Open its browser control tab, then use ordinary language in OtterDesk to inspect or control the visible robot. The stable Job agent reads the blueprint-owned control manual and invokes only the service's bounded MCP tools.

Version 5 composes ordinary command admission with the SDK's native async-device
transport and `mn.blocks.controlled_operation@1` named operation. Shared code handles request
journals, replay, uncertainty fencing and bounded async transport. Browser physics,
lease/readiness policy, live completion receipts and the priority stop path remain
domain-owned. It requires main SDK and blocks `>=1.3.61.dev27,<2`, with common
`>=1.3.61.dev25,<2`. Offline tests use
the real MCP/SDK/bridge path with a synthetic browser sender; this migration has
not been qualified in a live simulator browser session.

## Start the demo

```bash
mn blueprint run microduck_controller --detached
```

Run with `--web-ui` and open the emitted OtterDesk Job URL. That page frames the simulator through its Job-scoped proxy; it is the only supported browser entry point. The page plays the normal simulator boot and entrance automatically. Its lower-left MCP indicator progresses from `MCP CONNECTED`/`MCP WAITING` to `MCP READY` once this first tab holds the control lease and the simulator can accept motion.

In a multi-node cluster, launch this live UI on the node serving the OtterDesk Web UI (use `mn node list` to find its node name, then pass `--node <node-name>`). The job UI proxy reaches the worker through that node's private Docker network. The simulation runs in the browser and does not require a worker GPU.

Microduck declares `metadata.init_config_review.required: false`, so hiring does not pause for configuration confirmation. OtterDesk treats that declaration generically for any co-worker: the co-worker is launch-ready immediately while optional advanced settings remain available later in Configure.

In OtterDesk, try “move forward,” “turn left,” “find the ball,” “please free play,” “switch to rollers,” “spawn the ball,” “sit down,” or “stop.” The Job response agent uses the same-node LiteLLM proxy's resolved `default` route; the blueprint declares no runtime model dependency, and the desktop app does not run a second model, parse command keywords, or call the simulator directly. One conversation turn can issue at most one effect, and every effect is shown with a structured action receipt.

The authoritative manual is `knowledge/user_manual.md`. The same file is indexed as Job knowledge and exposed by MCP as the the shared Job manual resource and the `get_user_manual` tool. This keeps natural-language planning and direct MCP clients on one capability and safety contract.

The planner contract matches semantic intent rather than exact command text. Its examples are non-exhaustive, so conversational variants such as “free play now,” “let's free play,” “you can free play,” “could you locate the ball?”, “take a little step ahead,” and equivalent paraphrases for every declared control map to the same exact tools and enum arguments. It clarifies only material ambiguity and never asks for canonical wording. The manual still gives the default model strict flat JSON shapes for every tool; `command_id` remains runtime-owned. Structured planner calls forward temperature zero so the same prompt does not drift between `query`, `clarify`, and `action`.

The domain tools and their shared manual/polling entry points are `get_user_manual`, `get_duck_state`, `move_duck`, `perform_routine`, `find_ball`, `start_free_play`, `get_operation_status`, `stop_duck`, `set_locomotion`, `set_posture`, `play_ball_action`, and `reset_simulation`. Primitive motion uses fixed direction and duration enums or a named bounded routine. A request to move to the ball selects `find_ball`, not a single forward step. `set_posture` sits or stands using the simulator posture policy; sitting requires legged locomotion. `find_ball` is one composite effect: the LLM selects it from natural-language intent, then deterministic browser code continuously reads simulator-local duck/ball positions, corrects yaw, approaches the active ball, settles within 0.22 m, and stops. The loop is bounded to 30 seconds and 5 m of observed travel. It uses ground-truth positions, not camera perception, and it does not spawn or kick the ball. `start_free_play` reuses that bounded approach in legged mode, alternates left/right kicks, reacquires the moving ball, and repeats until `stop_duck`; it never spawns a missing ball. Its monitored operation completes after the first successful kick so chat can answer while play continues in the browser. Every effect uses a fresh UUID and is monitored through `get_operation_status`; an accepted receipt is never treated as proof of completion.

## Network and runtime notes

The simulator listener uses an OS-selected port in the DockerWorker's private runtime network. Its unique worker DNS address and port are supplied only to the shared Web UI skill and a HostLocal MCP sidecar. The sidecar accepts only Core loopback and Docker's discovered host-port gateway, while it is advertised and health-checked only as `127.0.0.1`. It rewrites the private upstream `Host` header to loopback so FastMCP's DNS-rebinding guard remains enabled. The browser receives the OtterDesk Job-scoped iframe proxy, while the Job agent resolves the declared `microduck-controller-mcp` service through the runtime registry. Neither path exposes the private upstream address to the desktop renderer.

To make the simulator directly reachable on a trusted LAN, set `web_ui.service.trusted_lan_enabled` to `true`, then set `host`, `listen_host`, `public_host`, and `public_url` in a local override and protect that network boundary: the MCP endpoint is intentionally unauthenticated.

The original application loads MuJoCo and ONNX runtime WASM from jsDelivr, so the browser needs egress to that CDN. No ROS, GPU, external simulator backend, or physical robot is required.

`payloads/web_app` is the readable simulator source. The identical, modified source, control manual, and service modules are also staged under `payloads/docker_worker` because the DockerWorker runtime deliberately builds only that directory as its image context. Both copies exclude local `node_modules` and generated `dist` output.

Version 1.2.1 includes the conversation guide in the DockerWorker's knowledge
folder and uses `@/examples/sample_inputs` for the bundled demo folder, so its
path remains valid when the package is installed outside the source checkout.

The service produces `web_ui.json`, `duck_service_state.json`, and `duck_command_history.json` in its run directory. The HostLocal sidecar uses `mn-python-sdk-web-ui` to publish the actual endpoint to the durable Job UI handle and forwards only `/health` and `/mcp` to the registered control service. See [SPEC.md](SPEC.md) and [TERM.md](TERM.md) for the exact control and safety contract.

The default host output folder is `~/Downloads/microduck-controller`.

Version 5.0.1 fixes startup when the execution and physical workflow IDs differ.
The simulator and Web UI registrar use the same physical run-output directory.
Deploy the matching Core HostLocal and Web UI SDK fixes and update the idle Job
definition before starting this version. Existing data does not need a reset.

## Validation

```bash
npm --prefix payloads/web_app run build
.venv/bin/python -m pytest tests/test_microduck_controller.py -q
jq empty manifest.json
jq empty config/default.json
```

## Block composition (5.0.0)

The service phase now uses the monitored-service block, and the terminal phase uses a domain-operation block. `domain/service_lifecycle.py` owns the ASGI listener resource; the SDK owns supervision, replay, health and shutdown. Command admission retains its controlled-operation block and priority stop path. Both staged source copies match. Health is checked every 60 seconds, bounded by 1,000,000 cycles and 64 MiB of checkpoints; rotate before capacity is exhausted.

Command admission selects the SDK's native `async_device` transport, with no
blueprint capability adapters. `BridgeHub` implements typed device observations
and exact-command receipts; the SDK owns async calls, reconciliation and the
pending-command invalidation check. The blueprint retains motion validation,
lease rules and cancellation messages. Main SDK and blocks must both be
`>=1.3.61.dev27,<2`; common remains `>=1.3.61.dev25,<2`. Browser receipts still
establish actual completion, separately from durable admission evidence.

## Blueprint package format

This blueprint uses the canonical blueprint/v1 format in both folders and ZIPs.
`manifest.json` contains identity, semantic release version, and document references.
`workflow.json` owns logical topology and policies; `execution.json` owns workers,
resources, and services; `contracts.json` owns input/output and artifact contracts.
Platform descriptors live in `extensions/`, package requirements in
`dependencies.json` when present, and operator defaults in `config/default.json`.
The SDK reads these documents together and compiles the Core execution artifact.
A ZIP contains the same files as the folder. Local overrides and invocation
configuration are resolved by the SDK before launch.

## Context engine contract

The `mn.context` descriptor explicitly disables Membrane runtime recall for this blueprint: its payload does not call TextMemory. Existing domain knowledge/RAG, live status, MCP controls, and Core coordination retain their own contracts. The retired conversation-memory declaration is removed, so this workflow does not start a context compressor or require a Membrane SDK merely to launch. Any future runtime-memory consumer must declare `mirrorneuron-python-sdk[context]`, ingest complete preprocessed text under trusted job/run scope, and use the Markdown/DuckDB CPU service.

## Standard MCP supervision

This package requires `mn.mcp.supervision.v1`. The SDK implements the shared manual, capabilities, context, results, activity, lifecycle, and operation tools. `knowledge/user_manual.md` is bundled with the prepared Job. Domain tools and their native JSON input/output schemas are declared once in `extensions/mcp.json`; response agents derive their bindings from it. All tool results use `mn.mcp.tool_result.v1`. Mutations require a request ID, and asynchronous work is observed through `get_operation_status`. Upgrade the installed SDK/API/desktop together and update idle Job definitions before using this contract.

## Live startup contract (5.1.0)

The simulator and its HostLocal control/UI registrar both use the shared
monitored-service lifecycle. The registrar's ready hook checks the page and code
assets; opening a browser is not a startup prerequisite. SDK-owned lifecycle
receipts finish startup progress without completing the live run, and shutdown
clears the UI claim. The final artifact step remains real shutdown work.
Requires coordinated SDK/blocks/Web UI dev32 or later and the matching API/Core/
proxy changes. Update an idle Job definition before starting; retain its identity
and saved data. No reset or blueprint-specific desktop bypass is needed.
