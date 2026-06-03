# Generic Customer Service Voice AI Co-worker SPEC

## Problem

Customer teams need a reusable voice co-worker that can speak with users through
a browser, answer from business-owned knowledge, and run on the local NVIDIA
Spark box without becoming a one-off demo.

## Outcome

The blueprint runs a Spark-hosted HTTPS/WebRTC page at
`https://192.168.4.173:7863/customer-service`. Customers can talk to the
co-worker through the browser. Operators can edit the run-scoped knowledge text
in the same page, and later turns retrieve from the updated text.

## Architecture

- Local OtterDesk blueprint and Gradio dashboard.
- Spark runtime node constrained to `mn2@192.168.4.173`.
- Shared NVIDIA stack from `/home/homer/Sandbox/nemotron-january-2026`.
- Pipecat SmallWebRTC over HTTPS.
- NVIDIA Parakeet ASR.
- Nemotron vLLM through an OpenAI-compatible API.
- Magpie TTS.
- Plain-text lexical RAG with per-turn snippet injection.

## RAG Contract

The authoritative editable knowledge for a run is:

`~/.mn/runs/<run_id>/knowledge/customer_service_knowledge.txt`

The service chunks this text locally and retrieves top matching chunks with a
small lexical scorer before each LLM turn. The LLM is instructed to answer from
retrieved snippets, ask clarifying questions when needed, and recommend
escalation when the answer is not grounded in knowledge.

## Limits

- v1 uses plain text and lexical retrieval, not a vector database.
- Self-signed HTTPS is expected for local WebRTC testing.
- The co-worker recommends human handoff but does not approve refunds, change
accounts, make legal or medical judgments, or execute customer-impacting actions.
- The shared NVIDIA ASR/LLM/TTS stack may be started or reused, but post-launch
cleanup stops only blueprint-owned voice-service processes.

## Evaluation

- Manifest and catalog tests pass.
- RAG chunking/retrieval and knowledge persistence tests pass.
- Spark is reachable as `homer@spark`.
- Spark has an NVIDIA GPU.
- `/health`, `/api/knowledge`, and `/customer-service` respond on Spark.
- Editing knowledge changes later answers.

