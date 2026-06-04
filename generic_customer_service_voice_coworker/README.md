# Pizza Order Voice AI Co-worker

This OtterDesk blueprint launches a warm pizza-ordering HTTPS/WebRTC voice page
backed by NVIDIA Parakeet ASR, Docker Model Runner LLM service, Magpie TTS, and editable
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
| `voice_https_port` | HTTPS/WebRTC port. Default: `7863`. |
| `voice_local_proxy_port` | Local HTTPS proxy port. Default: `7863`. |

## NVIDIA Runtime

The service is NVIDIA-bound:

- Execution profile: `nvidia-accelerated-voice`
- Required GPU: `gpu_count: 1`
- Required node capability: DGX Spark, GH200, H100, H200, B200, or GB200 class NVIDIA hardware
- LLM model alias: `otterdesk-voice-llm:default`
- ASR/TTS service aliases: `otterdesk-voice-asr:default`, `otterdesk-voice-tts:default`
- Default voice page: `https://localhost:7863/customer-service`

The pre-launch hook prepares `~/.mn/runs/<run_id>/knowledge/customer_service_knowledge.txt`
and writes local web UI metadata. The runtime voice node runs on an eligible
NVIDIA cluster node and serves:

- `GET /customer-service`
- `POST /api/offer`
- `GET /api/knowledge`
- `POST /api/knowledge`
- `GET /health`

For a cold NVIDIA stack, launch with a longer runtime timeout:

```bash
MN_PRE_LAUNCH_TIMEOUT_SECONDS=900 NEMOTRON_PRELAUNCH_WAIT_SECONDS=900 mn run generic_customer_service_voice_coworker
```

## Cluster Notes

Start a cluster node advertising one of the required NVIDIA capabilities above.
The local dashboard links to the localhost HTTPS page, while model lifecycle is
handled by `mn model` and Docker Model Runner.

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
