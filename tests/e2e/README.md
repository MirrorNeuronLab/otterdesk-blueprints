# Conversation experience E2E

The deterministic CCTV panel test needs only the sibling desktop's Playwright
dependency and installed Chromium; it uses a local SSE fixture and no runtime or
model. From the catalog root, run:

```bash
node ../otterdesk-desktop-app/node_modules/@playwright/test/cli.js test --config tests/e2e/cctv-media.config.cjs
```

This opt-in suite reads every published package from `index.json`, including
General Assistant, and uses the installed runtime plus the sibling desktop app.
It hires through the GUI, asks a real setup question, selects declared samples or
test-owned inputs, observes work and artifacts, and asks about the saved result.
Screenshots cover 1,180- and 1,440-pixel windows and resizing in both directions.

The conversation model is the desktop's actual cached CPU model. Its existing
engine and GGUF are cloned into each isolated profile; their normal verification
and inference still run. Downloads and external desktop account calls are
disabled. Domain execution uses the runtime's existing `--fake-llm --fake-skill`
mode. This tests workflow delivery and explanations, not scientific, financial,
clinical or physical-world accuracy. Native behavior that has no fake adapter
retains its declared boundary; Mac findings must remain in its local report.

Requirements: a built desktop checkout with its declared development dependencies,
a running local MirrorNeuron runtime and its execution nodes, `mn-api`, and the
already cached desktop conversation model. The desktop checkout defaults to the
sibling `otterdesk-desktop-app`; set `OTTERDESK_APP_ROOT` to use another location.
Set `BLUEPRINT_CONVERSATION_CACHE` if its existing model cache is elsewhere.

```bash
node tests/e2e/run.cjs --list
node tests/e2e/run.cjs
node tests/e2e/run.cjs --grep 'financial_advisor:'
```

`BLUEPRINT_E2E_OUTPUT` selects the evidence folder; its default is
`/private/tmp/otterdesk-blueprint-experience-e2e`. Do not place generated evidence
in tracked source folders. Each case records screenshots, visible conversation,
question/reply observations, output verification receipts and preparation status.
The model-boundary observer saves only static draft field names, mode choices and
a setup-prompt digest; it never saves draft values or raw inference/IPC payloads.
A separate observer records only whether a Job question started/completed, with
the published blueprint identity. A live service must actually dispatch its state
question through its Job; a generic answer asking the user to wait until the
service ends does not pass that check. The observer never changes a response.

Batch output checks require the declared non-optional Markdown reports as well
as a verified result receipt. An arbitrary non-empty file cannot establish report
delivery. Job responders may inherit the runtime's fake model; a reply containing
only `Simulated model response.` fails the explanation check and cannot establish
language quality. Direct desktop setup replies still use the real cached model.

For a deliberate check of normal Job replies, `BLUEPRINT_E2E_FAKE_LLM=0` omits the
fake LLM flag and retains fake skills. This uses the blueprint's configured
provider, so first verify its local model is already installed. This is a test
setting, not a runtime or blueprint override. For example:

```bash
BLUEPRINT_E2E_FAKE_LLM=0 node tests/e2e/run.cjs --grep '\bmac_security_investigator:'
```

The API, desktop profile, inputs and output home are isolated. Only Jobs proven
owned by returned test receipts are cancelled/deleted. An unconfirmed launch or
cleanup failure stops further launches and retains recovery context. The runner
also reconciles worker-owned receipts after an interrupted test before closing
the isolated API. Existing co-workers and installed runtime source are unchanged.

Help questions must preserve confirmed values and source selection. A preparation
failure is a failure, with its explanation reviewed separately; it never counts
as a completed co-worker journey. Inspect every transcript and screenshot before
claiming experience quality: green transport and artifact checks alone are
insufficient.
