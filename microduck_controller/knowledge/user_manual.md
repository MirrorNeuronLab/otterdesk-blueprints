# Microduck control manual

Microduck Controller operates one browser-based simulation. It never controls a physical robot. OtterDesk uses an LLM to translate a clear natural-language request into one declared MCP tool call. The running service, not conversational prose, is authoritative for connection state and command completion.

## Match meaning, not exact wording

Infer the user's semantic intent. Every phrase in this manual is a non-exhaustive example, not a required command string or keyword trigger. Do not ask the user to repeat a canonical phrase or name an MCP tool when one supported intent is already clear.

- Ignore polite or conversational framing such as “please,” “now,” “could you,” “would you,” “let's,” “you can,” “I'd like you to,” and “why don't you.”
- Treat question-shaped requests to make the duck act, such as “Can you find the ball?”, as actions. Treat questions about abilities or observed state as reads or answers, not actions.
- Resolve ordinary synonyms, tense, word order, filler words, capitalization, and punctuation by meaning. Preserve only the exact tool name and declared enum values in planner JSON.
- Choose an action when one supported effect and all required arguments are clear. Clarify only genuine ambiguity, such as a turn with no left/right direction; wording variation alone is not ambiguity.
- Context disambiguates ball intent: approach it once uses `find_ball`; kick once uses `play_ball_action`; repeatedly find, kick, and continue playing uses `start_free_play`.

For example, “free play now,” “let's free play,” “you can free play,” “go play with the ball,” and “keep chasing and kicking it” all select `start_free_play`. The planner returns exactly `{"intent":"action","tool":"start_free_play","arguments":{}}`; the built-in conversation runtime supplies the private command UUID. Likewise, “Can you find the ball?”, “move the duck to the ball,” “go over to the ball,” and “locate it for me” select `find_ball` and return `{"intent":"action","tool":"find_ball","arguments":{}}`.

## Before every action

Call `get_duck_state`. An action is allowed only when both `connected` and `ready` are `true`. If either is false, explain that the browser control tab must remain open and ready; do not call an effect tool. Use `stop_duck` immediately when the operator asks to stop.

Each external effect requires a fresh caller-generated `request_id`. Identical retries reuse it; conflicting reuse fails. The SDK maps it to a private worker UUID. A queued or accepted receipt does not prove motion completed. Poll the returned `operation_id` with `get_operation_status` and report only the observed terminal state.

An unknown outcome means the admission reply or current browser history is
unavailable. Keep observing that operation; do not issue another effect to
reconstruct it or claim it failed without evidence. A disconnected caller does
not cancel an already issued command. Use `stop_duck` when the operator asks to
stop; it bypasses ordinary request admission and remains available while busy.

## Natural-language controls

- Requests to go or walk forward/ahead, back up/reverse, or turn/rotate left or right use `move_duck` only when no destination is named. Conversational forms such as “take a little step ahead” and “could you turn to your right now?” mean the same thing.
- `direction` is exactly `forward`, `backward`, `turn_left`, or `turn_right`.
- `duration` is exactly `short` (250 ms), `medium` (500 ms), or `long` (1000 ms). “A little,” “brief,” or “small step” means `short`; “long” or “a big step” means `long`; use `medium` when no duration is expressed. Ask for clarification if a request could mean more than one direction.
- Requests to demonstrate, show off, do a demo, or do some moves use `perform_routine` with `showcase`. Spin-left, spin-right, zig-zag, or weaving requests use `spin_left`, `spin_right`, or `zigzag` when the direction/pattern is clear.
- Requests to walk on feet, use legs, or leave wheel mode use `set_locomotion` with `legs`. Requests to use wheels, rollers, drive, or skate use `rollers`.
- Requests to spawn, bring out, create, or make the ball appear use `play_ball_action` with `spawn_ball`. A single left-foot or right-foot kick uses `kick_left` or `kick_right`.
- Requests to find, locate, seek, approach, reach, chase down once, go over to, or move the duck to the ball use one `find_ball` call. This continuously navigates until the duck reaches the ball; one `move_duck` forward step does not fulfill it. Never expand this goal into repeated `move_duck` calls.
- Requests to sit, sit down, take a seat, or seat down use `set_posture` with `sit`. Requests to stand, stand up, or get up use `set_posture` with `stand`. Sitting requires legged locomotion.
- `find_ball` approaches an already-active ball using simulator-local duck and ball positions. It does not use a camera, spawn the ball, or kick it.
- The browser recalculates the target bearing on every control tick, supports both legs and rollers, settles within 0.22 m, and stops after 30 seconds or 5 m of observed travel.
- Requests to free play, play with the ball, keep playing, or repeatedly find/chase and kick the ball use one `start_free_play` call. This includes suggestions and permission statements such as “let's free play” and “you can free play.” Never expand this continuous goal into repeated `find_ball` or `play_ball_action` calls.
- `start_free_play` requires legged locomotion and an already-active ball. It uses the same bounded navigation loop, alternates left and right kicks, then reacquires the ball and repeats until `stop_duck` is called. It never spawns a missing ball.
- A completed `start_free_play` receipt means the first find-and-kick cycle succeeded and continuous play is running. It does not mean free play has stopped. Call `stop_duck` to end it.
- Requests to reset, restart, start over, or return the simulation to its beginning use `reset_simulation`.
- Requests to stop, stop everything, stop playing, freeze, halt, hold it, or saying “that's enough” use `stop_duck`. It immediately cancels free play, zeros remote movement, and ends an in-progress remote kick.
- Questions about capabilities or available controls are answered from this manual without invoking an effect. Explicit requests to read/show the manual use `get_user_manual`. Questions about current pose, location, mode, locomotion, ball, readiness, or command state use `get_duck_state`.

## Exact planner output shapes

These intent examples describe the built-in conversation planner. It omits the private `command_id` added by the trusted runtime. External MCP clients call the declared tools directly and must supply `request_id` on effects.

- Capability explanation: use an `answer` intent grounded in this installed manual. External clients can read the manual with the shared `get_user_manual` tool.
- State read: `{"intent":"query","tool":"get_duck_state","arguments":{}}`
- Bounded movement: `{"intent":"action","tool":"move_duck","arguments":{"direction":"forward","duration":"medium"}}`
- Named routine: `{"intent":"action","tool":"perform_routine","arguments":{"routine":"showcase"}}`
- Find once: `{"intent":"action","tool":"find_ball","arguments":{}}`
- Continuous play: `{"intent":"action","tool":"start_free_play","arguments":{}}`
- Stop everything: `{"intent":"action","tool":"stop_duck","arguments":{}}`
- Locomotion: `{"intent":"action","tool":"set_locomotion","arguments":{"locomotion":"rollers"}}`
- Posture: `{"intent":"action","tool":"set_posture","arguments":{"posture":"sit"}}`
- Ball action: `{"intent":"action","tool":"play_ball_action","arguments":{"action":"spawn_ball"}}`
- Reset: `{"intent":"action","tool":"reset_simulation","arguments":{}}`

One conversation turn may issue at most one effect. `find_ball` and `start_free_play` are composite effects, not sequences of primitive effects. If the user requests unrelated effects together, ask which one to perform first. Never invent raw velocity, distance, coordinates, joint control, browser automation, JavaScript, shell commands, physical-robot control, or a tool not listed here.

## Tool results

External tool calls return `mn.mcp.tool_result.v1` in `structuredContent`. Its typed `data` contains the domain `mn.microduck.command_receipt.v1`; its public `operation_id` is distinct from the private command UUID. Navigation receipts may add a sanitized `progress` phase and an `mn.microduck.navigation_result.v1` result. Preserve the tool name, validated arguments, confirmation metadata, command state, result, and failure reason in the action receipt. Treat `rejected`, `failed`, `cancelled`, and `timed_out` as unsuccessful outcomes. Do not claim that the duck moved merely because the request was accepted. Only a validated successful `find_ball` result may return “I found the ball! I’m tired, but I made it.”

## Supervision

Use `get_capabilities` for the current tools and their availability. Common MCP actions are implemented by the SDK. `start_run` starts new work, `pause_run` preserves a resumable run, `resume_run` continues it, and `stop_run` terminates it. Domain stop actions affect their named resource only. Accepted actions are not evidence of completion; use `get_operation_status`.

External mutations require a caller-generated `request_id`. Tool results use `mn.mcp.tool_result.v1` in `structuredContent`; keep workflow state inside `data` and poll a returned `operation_id` with `get_operation_status`. The runtime also publishes this installed manual through its MCP Skills manifest.
