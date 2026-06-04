#!/usr/bin/env python3
"""HTTPS launcher for the generic customer-service WebRTC voice co-worker."""

from __future__ import annotations

import json
import os
import ssl
import sys
import urllib.request
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pipecat.runner.run import _create_server_app


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from bot_customer_service_vllm import bot  # noqa: E402,F401
from conversation_events import emit_event, emit_log, run_dir, utc_now  # noqa: E402
from customer_service_web import register_customer_service_routes  # noqa: E402
from knowledge_store import ensure_knowledge_file, knowledge_metadata, read_knowledge, write_knowledge  # noqa: E402


def _http_probe(url: str, *, timeout: float = 2.0) -> dict[str, Any]:
    try:
        request = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(512).decode("utf-8", errors="replace")
            return {"ok": 200 <= response.status < 500, "status": response.status, "body": body[:200]}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def service_health() -> dict[str, Any]:
    dmr_base = (os.getenv("MN_LLM_API_BASE") or "http://localhost:12434/engines/v1").rstrip("/")
    asr_health = os.getenv("NVIDIA_ASR_HEALTH_URL", "http://127.0.0.1:8080/health")
    llm_health = os.getenv("NVIDIA_LLM_HEALTH_URL", f"{dmr_base}/models")
    tts_health = os.getenv("NVIDIA_TTS_HEALTH_URL", "http://127.0.0.1:8001/health")
    upstream = {
        "asr": _http_probe(asr_health),
        "llm": _http_probe(llm_health),
        "tts": _http_probe(tts_health),
    }
    return {
        "ok": all(item.get("ok") for item in upstream.values()),
        "service": "generic_customer_service_voice_coworker",
        "run_id": os.getenv("CUSTOMER_SERVICE_RUN_ID") or os.getenv("MN_RUN_ID"),
        "public_url": os.getenv("CUSTOMER_SERVICE_PUBLIC_URL"),
        "knowledge": knowledge_metadata().as_dict(),
        "upstream": upstream,
        "ts": utc_now(),
    }


def write_voice_service_handle() -> None:
    target = run_dir() / "voice_service.json"
    payload = {
        "schema_version": "mn.blueprint.voice_service.v1",
        "blueprint_id": "generic_customer_service_voice_coworker",
        "run_id": os.getenv("CUSTOMER_SERVICE_RUN_ID") or os.getenv("MN_RUN_ID"),
        "public_url": os.getenv("CUSTOMER_SERVICE_PUBLIC_URL"),
        "health_url": os.getenv("CUSTOMER_SERVICE_HEALTH_URL"),
        "knowledge_path": str(knowledge_metadata().path),
        "conversation_path": str(run_dir() / "conversation.jsonl"),
        "events_path": str(run_dir() / "events.jsonl"),
        "started_at": utc_now(),
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def register_api_routes(app: FastAPI) -> None:
    @app.get("/health", include_in_schema=False)
    async def health():
        payload = service_health()
        emit_event("customer_service_voice_health_checked", {"ok": payload["ok"]})
        return JSONResponse(payload, status_code=200 if payload["ok"] else 503)

    @app.get("/api/knowledge", include_in_schema=False)
    async def get_knowledge():
        ensure_knowledge_file()
        metadata = knowledge_metadata().as_dict()
        emit_event("customer_service_knowledge_loaded", metadata)
        return {"text": read_knowledge(), "metadata": metadata}

    @app.post("/api/knowledge", include_in_schema=False)
    async def post_knowledge(request: Request):
        raw = await request.body()
        text = ""
        if raw:
            try:
                payload = json.loads(raw)
                if isinstance(payload, dict):
                    text = str(payload.get("text") or "")
                elif isinstance(payload, str):
                    text = payload
            except json.JSONDecodeError:
                text = raw.decode("utf-8", errors="replace")
        metadata = write_knowledge(text).as_dict()
        emit_event("customer_service_knowledge_updated", metadata)
        emit_log("pizza menu knowledge updated", metadata=metadata)
        return {"ok": True, "metadata": metadata}


def main() -> None:
    host = os.getenv("NEMOTRON_BOT_HOST", "0.0.0.0")
    port = int(os.getenv("NEMOTRON_BOT_PORT") or os.getenv("VOICE_HTTPS_PORT", "7863"))
    certfile = os.getenv("NEMOTRON_SSL_CERT", str(ROOT / "certs" / "customer-service.crt"))
    keyfile = os.getenv("NEMOTRON_SSL_KEY", str(ROOT / "certs" / "customer-service.key"))

    ensure_knowledge_file()
    app = _create_server_app(
        transport_type="webrtc",
        host=host,
        proxy=None,
        esp32_mode=False,
        whatsapp_enabled=False,
        folder=None,
        dialin_enabled=False,
    )
    register_api_routes(app)
    register_customer_service_routes(app)
    write_voice_service_handle()
    emit_event("customer_service_voice_started", {"port": port, "public_url": os.getenv("CUSTOMER_SERVICE_PUBLIC_URL")})

    print(f"Customer-service voice co-worker ready: https://{host}:{port}/customer-service")
    uvicorn.run(app, host=host, port=port, ssl_certfile=certfile, ssl_keyfile=keyfile)


if __name__ == "__main__":
    main()
