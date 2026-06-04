# Pizza Order Voice AI Co-worker SPEC

## Problem

Pizza shops need a reusable voice co-worker that can speak with callers through
a browser, answer from editable menu knowledge, collect basic order details, and
run on an eligible NVIDIA cluster node without becoming a one-off demo.

## Outcome

The blueprint runs an NVIDIA-hosted HTTPS/WebRTC page exposed locally at
`https://localhost:7863/customer-service`. Customers can talk to the co-worker
through the browser. Operators can edit the run-scoped menu knowledge text in
the same page, and later turns retrieve from the updated text.

## Architecture

- Local OtterDesk blueprint and Gradio dashboard.
- Runtime node constrained to DGX Spark, GH200, H100, H200, B200, or GB200 class NVIDIA capabilities.
- Pipecat SmallWebRTC over HTTPS.
- NVIDIA Parakeet ASR.
- Docker Model Runner LLM through an OpenAI-compatible API.
- Magpie TTS.
- Plain-text lexical RAG with per-turn snippet injection.

## RAG Contract

The authoritative editable knowledge for a run is:

`~/.mn/runs/<run_id>/knowledge/customer_service_knowledge.txt`

The service chunks this text locally and retrieves top matching chunks with a
small lexical scorer before each LLM turn. The LLM is instructed to answer from
retrieved snippets, ask one order question at a time when needed, and recommend
human handoff when the answer is not grounded in knowledge.

## Limits

- v1 uses plain text and lexical retrieval, not a vector database.
- Self-signed HTTPS is expected for local WebRTC testing.
- The co-worker recommends human handoff but does not approve refunds, collect
card numbers, make allergen guarantees, make legal or medical judgments, or
finalize customer-impacting actions without a human.
- NVIDIA ASR/TTS services may be started or reused, while Docker Model Runner
serves the LLM. Post-launch cleanup stops only blueprint-owned voice-service processes.

## Evaluation

- Manifest and catalog tests pass.
- RAG chunking/retrieval and knowledge persistence tests pass.
- The cluster has an advertised DGX Spark, GH200, H100, H200, B200, or GB200 class NVIDIA node.
- `/health`, `/api/knowledge`, and `/customer-service` respond through localhost.
- Editing knowledge changes later answers.
