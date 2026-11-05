# {{BLUEPRINT_NAME}}

Runnable no-op starter for an OtterDesk co-worker. Its only step returns an
empty result. It makes no model calls, reads no user inputs and performs no
domain actions. MirrorNeuron still records normal workflow and block receipts.

Requires a ready MirrorNeuron runtime and Python 3.12 or newer. The runtime
prepares the dependencies declared in `dependencies.json`; no GPU is required.

## Run the starter

From this blueprint folder:

```bash
mn blueprint run --folder . --detached --follow-seconds 0
mn run show <run-id>
```

Expect one completed `do_nothing` step with an empty result and no domain
artifacts. Asking a question through the optional Chat response service uses
the runtime's configured model; the starter workflow does not.

Run the offline hook test without the SDK or a live runtime:

```bash
python3.12 -m unittest discover -s tests -v
```

## Add behavior

1. Write the mission, completion criteria and limits in `SPEC.md`.
2. Replace `payloads/domain/noop.py` with focused domain behavior. Its hook
   receives the stock block context and bounded inputs.
3. Declare inputs and outputs in `contracts.json`, logical steps in
   `workflow.json`, and block hooks and limits in `extensions/blocks.json`.
4. Add operator defaults to `config/default.json` and dependencies to
   `dependencies.json`. Keep secrets in local configuration or credential
   storage; `config/overwrite.json` is ignored.
5. Update this README, the user manual and tests before catalog publication.

`execution.json` selects the stock HostLocal Python worker. `payloads/steps/`
is reserved for custom `StepSpec` collaboration if a future step needs it.
Lifecycle, routing, retries and logical completion stay with MirrorNeuron.

This package lives at `{{OWNER}}/mn-blueprint-{{BLUEPRINT_ID}}` and is pinned
as a submodule in `otterdesk-blueprints`. It is not added to `index.json`
automatically. From the catalog root, use
`./scripts/git-push-all.sh "Describe the changes"` to publish blueprint changes
before updating the catalog pin.
