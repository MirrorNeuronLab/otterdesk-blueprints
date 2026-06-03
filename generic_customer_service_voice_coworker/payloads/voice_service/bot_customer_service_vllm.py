#!/usr/bin/env python3
"""Customer-service voice bot using NVIDIA ASR, Nemotron vLLM, and Magpie TTS."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger


ROOT = Path(__file__).resolve().parent
NEMOTRON_ROOT = Path(os.getenv("NEMOTRON_ROOT", "/home/homer/Sandbox/nemotron-january-2026"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(NEMOTRON_ROOT / "pipecat_bots"))

from customer_service_rag_processor import CustomerServiceRAGInjector
from knowledge_store import ensure_knowledge_file, read_knowledge
from conversation_events import append_conversation, emit_event

from magpie_websocket_tts import MagpieWebSocketTTSService
from nvidia_stt import NVidiaWebSocketSTTService
from sentence_aggregator import SentenceAggregator
from v2v_metrics import V2VMetricsProcessor

from pipecat.audio.turn.smart_turn.base_smart_turn import SmartTurnParams
from pipecat.audio.turn.smart_turn.local_smart_turn_v3 import LocalSmartTurnAnalyzerV3
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair
from pipecat.processors.frameworks.rtvi import RTVIConfig, RTVIObserver, RTVIProcessor
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.transports.daily.transport import DailyParams
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams


load_dotenv(override=True)

NVIDIA_ASR_URL = os.getenv("NVIDIA_ASR_URL", "ws://127.0.0.1:8080")
NVIDIA_LLM_URL = os.getenv("NVIDIA_LLM_URL", "http://127.0.0.1:8000/v1")
NVIDIA_LLM_MODEL = os.getenv(
    "NVIDIA_LLM_MODEL",
    "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16",
)
NVIDIA_LLM_API_KEY = os.getenv("NVIDIA_LLM_API_KEY", "not-needed")
NVIDIA_TTS_URL = os.getenv("NVIDIA_TTS_URL", "http://127.0.0.1:8001")
VAD_STOP_SECS = float(os.getenv("VAD_STOP_SECS", "0.2"))


transport_params = {
    "daily": lambda: DailyParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
        vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=VAD_STOP_SECS)),
        turn_analyzer=LocalSmartTurnAnalyzerV3(params=SmartTurnParams()),
    ),
    "twilio": lambda: FastAPIWebsocketParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
        vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=VAD_STOP_SECS)),
        turn_analyzer=LocalSmartTurnAnalyzerV3(params=SmartTurnParams()),
    ),
    "webrtc": lambda: TransportParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
        vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=VAD_STOP_SECS)),
        turn_analyzer=LocalSmartTurnAnalyzerV3(params=SmartTurnParams()),
    ),
}


def system_prompt() -> str:
    business_name = os.getenv("CUSTOMER_SERVICE_BUSINESS_NAME", "Acme Customer Care")
    service_scope = os.getenv(
        "CUSTOMER_SERVICE_SCOPE",
        "Answer common customer-service questions from the editable knowledge base.",
    )
    escalation_policy = os.getenv(
        "CUSTOMER_SERVICE_ESCALATION_POLICY",
        "Escalate anything not grounded in the knowledge base.",
    )
    opening_message = os.getenv(
        "CUSTOMER_SERVICE_OPENING_MESSAGE",
        f"Thanks for calling {business_name}. How can I help today?",
    )
    return f"""
You are the voice customer-service co-worker for {business_name}.

You speak naturally, briefly, and kindly. Keep responses under two spoken sentences unless the customer asks for detail.

Service scope:
{service_scope}

Editable knowledge rules:
- Use only the retrieved editable customer knowledge injected into each user turn.
- If the knowledge does not contain the answer, say you do not have that information and ask one clarifying question or recommend escalation.
- Never invent business policies, prices, schedules, account status, refunds, legal advice, medical advice, or safety instructions.
- If the user asks for an account change, refund approval, emergency support, legal/medical advice, or anything outside scope, recommend human handoff.

Escalation policy:
{escalation_policy}

Opening message:
{opening_message}
""".strip()


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments) -> None:
    ensure_knowledge_file()
    logger.info("Starting generic customer-service voice co-worker")
    logger.info(f"  ASR URL: {NVIDIA_ASR_URL}")
    logger.info(f"  LLM URL: {NVIDIA_LLM_URL}")
    logger.info(f"  LLM Model: {NVIDIA_LLM_MODEL}")
    logger.info(f"  TTS URL: {NVIDIA_TTS_URL}")

    stt = NVidiaWebSocketSTTService(url=NVIDIA_ASR_URL, sample_rate=16000)
    llm = OpenAILLMService(
        api_key=NVIDIA_LLM_API_KEY,
        base_url=NVIDIA_LLM_URL,
        model=NVIDIA_LLM_MODEL,
        params=OpenAILLMService.InputParams(
            temperature=float(os.getenv("LLM_TEMPERATURE", "0.2")),
            max_tokens=int(os.getenv("LLM_MAX_TOKENS", "140")),
            extra={
                "extra_body": {
                    "chat_template_kwargs": {"enable_thinking": False},
                }
            },
        ),
    )
    tts = MagpieWebSocketTTSService(
        server_url=NVIDIA_TTS_URL,
        voice=os.getenv("MAGPIE_VOICE") or os.getenv("CUSTOMER_SERVICE_VOICE", "aria"),
        language="en",
        params=MagpieWebSocketTTSService.InputParams(
            language="en",
            streaming_preset=os.getenv("MAGPIE_STREAMING_PRESET", "conservative"),
            use_adaptive_mode=True,
        ),
    )

    opening_message = os.getenv(
        "CUSTOMER_SERVICE_OPENING_MESSAGE",
        f"Thanks for calling {os.getenv('CUSTOMER_SERVICE_BUSINESS_NAME', 'Acme Customer Care')}. How can I help today?",
    )
    context = LLMContext(
        [
            {"role": "system", "content": system_prompt()},
            {
                "role": "user",
                "content": (
                    "Greet the customer with the opening message below, then ask what they need. "
                    f"Opening message: {opening_message}"
                ),
            },
        ]
    )
    context_aggregator = LLMContextAggregatorPair(context)
    rtvi = RTVIProcessor(config=RTVIConfig(config=[]))
    rag_injector = CustomerServiceRAGInjector()
    sentence_aggregator = SentenceAggregator()
    v2v_metrics = V2VMetricsProcessor(vad_stop_secs=VAD_STOP_SECS)

    pipeline = Pipeline(
        [
            transport.input(),
            rtvi,
            stt,
            rag_injector,
            context_aggregator.user(),
            llm,
            sentence_aggregator,
            tts,
            v2v_metrics,
            transport.output(),
            context_aggregator.assistant(),
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=16000,
            audio_out_sample_rate=24000,
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
        observers=[RTVIObserver(rtvi)],
        idle_timeout_secs=runner_args.pipeline_idle_timeout_secs,
    )

    @rtvi.event_handler("on_client_ready")
    async def on_client_ready(rtvi):
        logger.info("RTVI client ready; greeting customer")
        emit_event("customer_service_voice_ready", {"knowledge_bytes": len(read_knowledge().encode("utf-8"))})
        await rtvi.set_bot_ready()
        await task.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Client disconnected")
        emit_event("customer_service_turn_completed", {"status": "client_disconnected"})
        await task.cancel()

    runner = PipelineRunner(handle_sigint=runner_args.handle_sigint)
    try:
        await runner.run(task)
    finally:
        append_conversation("system", "voice_session_closed")


async def bot(runner_args: RunnerArguments) -> None:
    transport = await create_transport(runner_args, transport_params)
    await run_bot(transport, runner_args)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()

