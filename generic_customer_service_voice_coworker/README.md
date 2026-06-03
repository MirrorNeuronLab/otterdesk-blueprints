# Pizza Order Voice AI Co-worker

This OtterDesk blueprint launches a warm pizza-ordering HTTPS/WebRTC voice page
backed by NVIDIA Parakeet ASR, Nemotron vLLM, Magpie TTS, and editable
plain-text menu RAG knowledge.

The local shared OtterDesk/Gradio dashboard stays enabled and records the
localhost voice link, service health, event stream, menu knowledge snapshot,
conversation log, and final run artifact.

## Inputs

| Input | Purpose |
| --- | --- |
| `business_name` | Name the co-worker uses with callers. |
| `service_scope` | Boundaries for what it should help with. |
| `opening_message` | First spoken message when the customer connects. |
| `knowledge_text` | Initial editable RAG knowledge for the run. |
| `escalation_policy` | Rules for recommending human handoff. |
| `voice` | Magpie voice or preset. |
| `spark_host` | SSH target for Spark. Default: `homer@spark`. |
| `voice_https_port` | Spark HTTPS/WebRTC port. Default: `7863`. |
| `voice_local_proxy_port` | Local HTTPS proxy port. Default: `7863`. |

## Spark Runtime

The service is GPU/Spark-bound:

- Execution profile: `customer-service-voice-nvidia`
- Required GPU: `gpu_count: 1`
- Default node target: `mn2@192.168.4.173`
- Default voice page: `https://localhost:7863/customer-service`
- Spark backend: `mn2@192.168.4.173` serves port `7863` behind the localhost tunnel.

The pre-launch hook connects to `homer@spark`, starts or reuses
`/home/homer/Sandbox/nemotron-january-2026/scripts/nemotron.sh start --mode vllm`,
prepares `~/.mn/runs/<run_id>/knowledge/customer_service_knowledge.txt`, and
writes local web UI metadata, including a local SSH proxy so browser traffic can
use localhost. The runtime voice node runs on Spark and serves:

- `GET /customer-service`
- `POST /api/offer`
- `GET /api/knowledge`
- `POST /api/knowledge`
- `GET /health`

For a cold NVIDIA stack, launch with a longer pre-launch timeout:

```bash
MN_PRE_LAUNCH_TIMEOUT_SECONDS=900 NEMOTRON_PRELAUNCH_WAIT_SECONDS=900 mn run generic_customer_service_voice_coworker
```

## Cluster Notes

Start the local node and add Spark as the second node with Spark advertising the
`customer-service-voice-nvidia` profile. The voice node is constrained to
`mn2@192.168.4.173`, and the local dashboard links to the localhost HTTPS page.

Code changes are made locally and synced to Spark through git only. Runtime
knowledge and conversation artifacts are copied through the blueprint hooks.

## Artifacts

- `web_ui.json`
- `voice_service.json`
- `knowledge/customer_service_knowledge.txt`
- `conversation.jsonl`
- `events.jsonl`
- `logs.jsonl`
- `final_artifact.json`

## Validation

```bash
python3 -m pytest -q
```

Manual acceptance:

1. Open `https://localhost:7863/customer-service`.
2. Allow microphone access.
3. Ask for a pizza and hear a response.
4. Edit the menu knowledge text, save it, and ask a question that depends on the edit.
