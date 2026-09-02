# Microduck Controller terms and safety boundary

Microduck Controller controls only the bundled, browser-based simulation. It
cannot control a physical Microduck or any other robot.

The public control surface is intentionally limited to compact state reads,
short forward/backward/turn plans, one bounded deterministic approach to an
already-active ball, a stoppable find-kick-reacquire loop, stop, locomotion
changes, reset, and ball spawn/kicks. Continuous free play requires an active
ball and legged locomotion, and every approach within it retains the navigation
time and travel bounds. It does not accept raw joint targets, raw velocity values, shell
commands, browser scripting, filesystem paths, or arbitrary network targets.

The first `?control=1` browser tab holds the simulation lease. MCP effects are
rejected when that tab is absent, stale, still booting, or busy. Disconnecting
the tab rejects in-flight remote work; an accepted receipt is not evidence that
a movement completed.

The service is unauthenticated because it binds to localhost by default. An
operator who changes the host/public URL for LAN access is responsible for a
trusted network boundary or firewall. The web client needs browser egress to
jsDelivr to load the existing MuJoCo and ONNX runtime WASM assets.

The bundled simulator is derived from the Microduck playground and includes
models and policies credited by its original README to Pollen Robotics and the
`pollen-robotics/microduck` and `pollen-robotics/microduck_rl` projects.
