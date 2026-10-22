# Microduck Controller specification

## Objective

Run a single live Microduck MuJoCo simulation in a browser and let the stable OtterDesk Job agent safely translate natural language into one bounded MCP read or effect. The agent uses the same-node LiteLLM proxy's resolved `default` route; the blueprint declares no runtime model dependency and the desktop does not require or own another LLM.

## Runtime contract

Version 5.0.1 resolves the simulator and registrar run-output directory using
Core's physical `MN_WORKFLOW_RUN_ID` under `MN_RUNS_ROOT`, matching the stock
block worker. An explicit `MN_RUN_DIR` remains authoritative. `MN_RUN_ID`
continues to identify the execution in artifacts and published results. Deploy
the matching Core HostLocal and Web UI SDK identity fixes before starting an
updated Job definition; no data reset is required.

The blueprint is a manually stopped service. The simulator reserves an OS-selected collision-free private HTTP port for each Run in its DockerWorker network. A HostLocal sidecar uses `mn-python-sdk-web-ui` to register the worker's private DNS endpoint plus its HTTP/WebSocket allowlist on the durable Job UI handle. The same sidecar binds inside the Core container so Docker's host-loopback publication can reach it, but accepts requests only from Core loopback or Docker's discovered host-port gateway; the runtime still advertises and health-checks only `127.0.0.1`. When forwarding, it connects to the private worker DNS endpoint while presenting a loopback `Host` header accepted by FastMCP's DNS-rebinding guard. It exposes only `/health` and `/mcp` on the declarative `microduck-controller-mcp` service so the Job response agent can resolve one passing, Run-scoped endpoint. The desktop renderer uses only OtterDesk's Job UI and Job MCP boundaries and never receives the private upstream address.

The simulator is at `/`, the control-mode view is at `/?control=1`, health is at `/health`, the browser bridge is `/bridge`, and the MCP endpoint is `/mcp`. The service Run starts immediately after hire and continues until paused or stopped; Conversation never starts, resumes, or restarts it.

The blueprint declares `metadata.init_config_review.required: false`. Hiring therefore needs no configuration confirmation and may proceed directly to setup and service launch. Its declared fields are optional advanced settings, not a first-run gate. This uses OtterDesk's generic contract for every co-worker that explicitly opts out; it is not a Microduck-specific desktop exception.

The browser owns all physics and policy execution. The service never runs MuJoCo, ONNX, or a synthetic simulator server-side. One ready browser tab can hold the control lease. It sends a bounded state snapshot five times per second; state older than one second is disconnected. A second tab is a spectator and cannot publish state or receive commands.

Version 5 declares `mn.blocks.operations.simulator_command` as a controlled
operation. SDK-owned request journals bind Core job/run/agent and command UUID,
with three capability calls and a 3-second attempt bound. The async binding admits at
most two ordinary requests, with no waiting queue and a 1-second transport deadline.
Stop runs directly through the existing browser bridge, bypasses ordinary
admission capacity and invalidates older unadmitted attempts. An interrupted MCP
caller does not discard an in-flight admission receipt or release its slot early.
The existing atomic bridge checks remain authoritative at actual dispatch.

An exact prior receipt is observed before new-state authorization; changed-ID
payloads conflict. Journaled admission is not completed motion: tool replies
project current browser receipts. A lost reply remains unknown and observable;
after a service restart, verified block evidence without current browser history
stays unknown rather than replaying an uncertain command. Invalid raw/named motion
still fails the domain protocol. Motion constants live once in domain/protocol;
the normal and Docker-context runtime sources remain identical. No source/sink,
workflow topology, MCP tool roster or browser control algorithm changed.

## MCP contract

The domain tools and their shared manual/polling entry points are `get_user_manual`, `get_duck_state`, `move_duck`, `perform_routine`, `find_ball`, `start_free_play`, `get_operation_status`, `stop_duck`, `set_locomotion`, `set_posture`, `play_ball_action`, and `reset_simulation`. Public effects take a caller-supplied `request_id`; the private simulation binding maps it to `command_id`. Retrying an identical command returns its original receipt; reusing an ID for a different effect is rejected.

`move_duck` accepts one `forward`, `backward`, `turn_left`, or `turn_right` direction and one `short`, `medium`, or `long` duration. These map to 250, 500, or 1,000 ms. `perform_routine` accepts only `showcase`, `spin_left`, `spin_right`, or `zigzag`; every predefined plan remains below five seconds. The browser maps those directions to the existing policy limits for the active legs or rollers mode. No raw velocity or joint command is available. Stop has priority and clears active remote movement, continuous free play, and an in-progress remote kick.

`set_posture` is a bounded sit/stand effect through the browser simulator; sitting requires legged locomotion and completion is confirmed by observed posture. A request to move the duck to the ball uses `find_ball`, not a single `move_duck` step.

`find_ball` is one `navigation` effect. The Job LLM maps find/seek/approach/go-to-ball intent to that tool and must not synthesize repeated `move_duck` calls. At the 50 Hz control loop, deterministic browser code recalculates bearing from simulator-local duck and active-ball x/y positions. It turns while angular error exceeds 0.30 radians, begins forward motion after alignment within 0.15 radians, returns to turning outside the wider threshold, and enters a zero-command settling phase within 0.22 m. Completion requires speed at or below 0.05 m/s for 250 ms. Legs and rollers use their existing velocity limits. Normal walk/drive mode and an active ball are required. Each attempt is bounded to 30 seconds and 5 m of observed travel, and stop, bridge disconnect, or stale state cancels it and zeros remote input.

`start_free_play` is one continuous `play` effect. The Job LLM maps free-play/play-with-the-ball intent to this tool and must not synthesize repeated `find_ball` or `play_ball_action` calls. It requires legged locomotion and an already-active ball. The browser runs the same bounded approach, kicks with alternating feet, waits for the kick and post-kick lock to finish, retargets the moved ball, and repeats. The monitored command completes only after the first successful kick, allowing Conversation to return `Free play started! I’ll keep finding and kicking the ball until you tell me to stop.` while the browser controller remains active. `stop_duck`, bridge disconnect, and stale state terminate the background controller and zero its input; `stop_duck` also ends an in-progress remote kick.

Compact state contains only connection/ready state, duck x/y/yaw/speed/mode/locomotion, ball active/x/y/distance, and bounded command receipts. Location is measured in simulator-local meters, not GPS. Neither head-camera pixels nor ToF readings are exposed. Effects need a fresh ready browser lease; kicks need legged locomotion. Locomotion, ball, reset, and navigation effects remain pending until the browser reports their observed terminal state or a bounded timeout. Navigation receipts may contain a sanitized phase and `mn.microduck.navigation_result.v1` metrics while retaining `mn.microduck.command_receipt.v1`.

## Conversation and manual contract

Version 1.2.1 stages the conversation guide alongside the manual in the
DockerWorker image. The default demo folder uses the SDK bundle-root reference
`@/examples/sample_inputs`.

`knowledge/user_manual.md` is the single human-readable control contract. MCP exposes it as the shared Job manual and `get_user_manual`; Job RAG indexes the same file. The Job agent receives the manual, exact user-tool declarations, live Job context, and recent conversation before asking the default model for one strict JSON plan. A turn may answer, clarify, read one tool, invoke one effect, or make one explicit bounded memory change. Invalid model output or an unavailable model results in no tool call.

Planner classification is semantic, not exact-match. Manual examples are non-exhaustive; polite/modal framing, suggestions such as “let's free play,” permission statements such as “you can free play,” synonyms, tense, word order, filler, capitalization, and punctuation do not change an otherwise clear supported intent. The LLM maps paraphrases across every declared tool, clarifies only material ambiguity, and emits one exact flat plan using declared enum values. For example, “Can you find the ball?”, “go over to the ball,” and “locate it for me” all produce `{"intent":"action","tool":"find_ball","arguments":{}}`; “free play now,” “let's free play,” and “you can free play” all produce `{"intent":"action","tool":"start_free_play","arguments":{}}`. The trusted runtime adds `command_id`. The primary LLM configuration forwards temperature zero through structured-output options so planner classification is repeatable on the default local route.

Every motion, navigation, play, locomotion, ball, and reset effect performs a fresh `get_duck_state` preflight and requires top-level `connected: true` and `ready: true`. Stop remains available as the emergency action. The response agent resolves exactly one passing `microduck-controller-mcp` service, verifies that its tool names and argument schemas exactly match the manifest, and then monitors command status. Tool receipts preserve validated arguments, command state, confirmation metadata, progress, results, and failure reasons for OtterDesk. A validated successful ball approach returns the server-authored message `I found the ball! I’m tired, but I made it.` A first successful free-play kick returns the server-authored start message while continuous control remains active until stop.

## Limits and artifacts

Version 1.1.1 sets the default host output folder to
`~/Downloads/microduck-controller`, matching the declared job name. Previously
submitted jobs retain their configured destination.

This is a software demonstration, not a physical-robot controller. It has no ROS, no server-side simulator backend, no general autonomous navigation, no camera-based perception, and no cross-Run command replay. Its goal-directed behaviors are the bounded deterministic approach to an already-active ball and the stoppable find-kick-reacquire loop built from that approach. Conversation planning belongs to the stable Job response service and uses only the same-node LiteLLM proxy's default route plus the blueprint's MCP contract and job-scoped RAG.

The service writes `web_ui.json`, `duck_service_state.json`, `duck_command_history.json`, and the normal final service artifact under the Run output. These artifacts contain no credentials or browser address details.

## Block composition (5.0.0)

The service phase now uses the monitored-service block, and the terminal phase uses a domain-operation block. `domain/service_lifecycle.py` owns the ASGI listener resource; the SDK owns supervision, replay, health and shutdown. Command admission retains its controlled-operation block and priority stop path. Both staged source copies match. Health is checked every 60 seconds, bounded by 1,000,000 cycles and 64 MiB of checkpoints; rotate before capacity is exhausted.

The controlled operation selects `transport: async_device` and declares no
capability adapters. Native `BridgeHub` methods return SDK `DeviceObservation`
and full-command `DeviceReceipt` values. The SDK owns loop/thread calls, receipt
envelopes, prior observation, reconciliation and loop-owned invalidation before
dispatch; a pure domain `cancel` hook supplies the Microduck cancellation receipt.
Missing current history preserves the unknown-effect fence. Stop bypasses ordinary
capacity and retains its atomic bridge policy. This contract requires main SDK
and blocks `>=1.3.61.dev27,<2`, with common `>=1.3.61.dev25,<2`.

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

## Shared service readiness (5.1.0)

`microduck_web_ui_registrar` is a canonical auxiliary monitored-service block.
Its domain hooks bind the private endpoint, MCP listener and exact UI readiness
probe; shared SDK code owns startup deadlines, lifecycle receipts, checkpoints,
cancellation and Web UI status invalidation. It reads the SDK-provided physical
run directory. The hosting computer's authenticated API relay serves remote
clients without exposing Docker DNS or listener ports. Startup ends when the
simulator and registrar are serving; `finalize_service` remains a shutdown phase.
Deploy matching SDK/blocks/Web UI dev32 and API/Core/proxy contracts together.
