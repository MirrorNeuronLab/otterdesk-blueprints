# Microduck Controller specification

## Objective

Run a single live Microduck MuJoCo simulation in a browser and let the stable OtterDesk Job agent safely translate natural language into one bounded MCP read or effect. The agent uses the same-node LiteLLM proxy's resolved `default` route; the blueprint declares no runtime model dependency and the desktop does not require or own another LLM.

## Runtime contract

The blueprint is a manually stopped service. The simulator reserves an OS-selected collision-free private HTTP port for each Run in its DockerWorker network. A HostLocal sidecar uses `mirrorneuron-web-ui-skill` to register the worker's private DNS endpoint plus its HTTP/WebSocket allowlist on the durable Job UI handle. The same sidecar binds inside the Core container so Docker's host-loopback publication can reach it, but accepts requests only from Core loopback or Docker's discovered host-port gateway; the runtime still advertises and health-checks only `127.0.0.1`. When forwarding, it connects to the private worker DNS endpoint while presenting a loopback `Host` header accepted by FastMCP's DNS-rebinding guard. It exposes only `/health` and `/mcp` on the declarative `microduck-controller-mcp` service so the Job response agent can resolve one passing, Run-scoped endpoint. The desktop renderer uses only OtterDesk's Job UI and Job MCP boundaries and never receives the private upstream address.

The simulator is at `/`, the control-mode view is at `/?control=1`, health is at `/health`, the browser bridge is `/bridge`, and the MCP endpoint is `/mcp`. The service Run starts immediately after hire and continues until paused or stopped; Conversation never starts, resumes, or restarts it.

The blueprint declares `metadata.init_config_review.required: false`. Hiring therefore needs no configuration confirmation and may proceed directly to setup and service launch. Its declared fields are optional advanced settings, not a first-run gate. This uses OtterDesk's generic contract for every co-worker that explicitly opts out; it is not a Microduck-specific desktop exception.

The browser owns all physics and policy execution. The service never runs MuJoCo, ONNX, or a synthetic simulator server-side. One ready browser tab can hold the control lease. It sends a bounded state snapshot five times per second; state older than one second is disconnected. A second tab is a spectator and cannot publish state or receive commands.

## MCP contract

The exact MCP tools are `get_user_manual`, `get_duck_state`, `move_duck`, `perform_routine`, `find_ball`, `free_play`, `get_command_status`, `stop_duck`, `set_locomotion`, `play_ball_action`, and `reset_simulation`. Every effect takes a caller-supplied UUID `command_id`. Retrying an identical command returns its original receipt; reusing an ID for a different effect is rejected.

`move_duck` accepts one `forward`, `backward`, `turn_left`, or `turn_right` direction and one `short`, `medium`, or `long` duration. These map to 250, 500, or 1,000 ms. `perform_routine` accepts only `showcase`, `spin_left`, `spin_right`, or `zigzag`; every predefined plan remains below five seconds. The browser maps those directions to the existing policy limits for the active legs or rollers mode. No raw velocity or joint command is available. Stop has priority and clears active remote movement, continuous free play, and an in-progress remote kick.

`find_ball` is one `navigation` effect. The Job LLM maps find/seek/approach/go-to-ball intent to that tool and must not synthesize repeated `move_duck` calls. At the 50 Hz control loop, deterministic browser code recalculates bearing from simulator-local duck and active-ball x/y positions. It turns while angular error exceeds 0.30 radians, begins forward motion after alignment within 0.15 radians, returns to turning outside the wider threshold, and enters a zero-command settling phase within 0.22 m. Completion requires speed at or below 0.05 m/s for 250 ms. Legs and rollers use their existing velocity limits. Normal walk/drive mode and an active ball are required. Each attempt is bounded to 30 seconds and 5 m of observed travel, and stop, bridge disconnect, or stale state cancels it and zeros remote input.

`free_play` is one continuous `play` effect. The Job LLM maps free-play/play-with-the-ball intent to this tool and must not synthesize repeated `find_ball` or `play_ball_action` calls. It requires legged locomotion and an already-active ball. The browser runs the same bounded approach, kicks with alternating feet, waits for the kick and post-kick lock to finish, retargets the moved ball, and repeats. The monitored command completes only after the first successful kick, allowing Conversation to return `Free play started! I’ll keep finding and kicking the ball until you tell me to stop.` while the browser controller remains active. `stop_duck`, bridge disconnect, and stale state terminate the background controller and zero its input; `stop_duck` also ends an in-progress remote kick.

Compact state contains only connection/ready state, duck x/y/yaw/speed/mode/locomotion, ball active/x/y/distance, and bounded command receipts. Location is measured in simulator-local meters, not GPS. Neither head-camera pixels nor ToF readings are exposed. Effects need a fresh ready browser lease; kicks need legged locomotion. Locomotion, ball, reset, and navigation effects remain pending until the browser reports their observed terminal state or a bounded timeout. Navigation receipts may contain a sanitized phase and `mn.microduck.navigation_result.v1` metrics while retaining `mn.microduck.command_receipt.v1`.

## Conversation and manual contract

`payloads/knowledge/microduck_user_manual.md` is the single human-readable control contract. MCP exposes it as `microduck://manual` and `get_user_manual`; Job RAG indexes the same file. The Job agent receives the manual, exact user-tool declarations, live Job context, and recent conversation before asking the default model for one strict JSON plan. A turn may answer, clarify, read one tool, invoke one effect, or make one explicit bounded memory change. Invalid model output or an unavailable model results in no tool call.

Planner classification is semantic, not exact-match. Manual examples are non-exhaustive; polite/modal framing, suggestions such as “let's free play,” permission statements such as “you can free play,” synonyms, tense, word order, filler, capitalization, and punctuation do not change an otherwise clear supported intent. The LLM maps paraphrases across every declared tool, clarifies only material ambiguity, and emits one exact flat plan using declared enum values. For example, “Can you find the ball?”, “go over to the ball,” and “locate it for me” all produce `{"intent":"action","tool":"find_ball","arguments":{}}`; “free play now,” “let's free play,” and “you can free play” all produce `{"intent":"action","tool":"free_play","arguments":{}}`. The trusted runtime adds `command_id`. The primary LLM configuration forwards temperature zero through structured-output options so planner classification is repeatable on the default local route.

Every motion, navigation, play, locomotion, ball, and reset effect performs a fresh `get_duck_state` preflight and requires top-level `connected: true` and `ready: true`. Stop remains available as the emergency action. The response agent resolves exactly one passing `microduck-controller-mcp` service, verifies that its tool names and argument schemas exactly match the manifest, and then monitors command status. Tool receipts preserve validated arguments, command state, confirmation metadata, progress, results, and failure reasons for OtterDesk. A validated successful ball approach returns the server-authored message `I found the ball! I’m tired, but I made it.` A first successful free-play kick returns the server-authored start message while continuous control remains active until stop.

## Limits and artifacts

This is a software demonstration, not a physical-robot controller. It has no ROS, no server-side simulator backend, no general autonomous navigation, no camera-based perception, and no cross-Run command replay. Its goal-directed behaviors are the bounded deterministic approach to an already-active ball and the stoppable find-kick-reacquire loop built from that approach. Conversation planning belongs to the stable Job response service and uses only the same-node LiteLLM proxy's default route plus the blueprint's MCP contract and job-scoped RAG.

The service writes `web_ui.json`, `duck_service_state.json`, `duck_command_history.json`, and the normal final service artifact under the Run output. These artifacts contain no credentials or browser address details.

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
