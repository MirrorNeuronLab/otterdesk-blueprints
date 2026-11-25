# Software verifier component

The Rust command targets the WASI 0.3 CLI world. Its imports in [worker.wit](wit/worker.wit) bind the six versioned skills from the `mn-skills` Cargo workspace. Each verifier blueprint ships its own command and skill components under `payloads/wasm`. The SDK pins the skill bytes before composing the executable.

Run the build from the catalog checkout with Rust 1.100.0, its `wasm32-wasip3` target and WAC 0.12.0 installed.

```sh
rustup target add --toolchain 1.100.0 wasm32-wasip3
python3 scripts/rebuild_verifier_wit.py --skills /path/to/mn-skills
```

A Wasmtime 51 executor receives operation configuration in `/job/config.json` and the invocation body in `/job/mirror_neuron_input.json`. The command writes a typed step result and exits nonzero on invalid input. Core owns workflow state, step dependencies, child-plan validation, retries and cancellation. The admission command reads the invocation and returns its mapped result. Each other phase runs once through the Wasmtime embedder and uses the WIT services granted to that step for durable artifacts, model inference, approvals or mailbox operations.
