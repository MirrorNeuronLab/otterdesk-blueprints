"""Trusted serving entrypoint; only SDK first-use startup reaches this code."""

import os

SOURCE_MODEL = "nvidia/NVIDIA-Nemotron-3.5-Transcribe-30B-A4B-NVFP4"
MODEL_REVISION = "66c6adc4020179567074d0399cda2a4eeb2bb347"


def main():
    import torch

    if not torch.cuda.is_available() or torch.cuda.get_device_capability()[0] not in {
        10,
        12,
    }:
        raise RuntimeError("This exact NVFP4 checkpoint requires NVIDIA Blackwell")
    from huggingface_hub import snapshot_download

    # Never fetch the BF16/FP8 siblings or an unpinned main revision.
    directory = snapshot_download(
        repo_id=SOURCE_MODEL, revision=MODEL_REVISION, max_workers=4
    )
    command = [
        "/opt/nemo/.venv/bin/vllm",
        "serve",
        directory,
        "--served-model-name",
        SOURCE_MODEL,
        "--host",
        "0.0.0.0",
        "--port",
        "8000",
        "--trust-remote-code",
        "--dtype",
        "bfloat16",
        "--kv-cache-dtype",
        "fp8",
        "--gpu-memory-utilization",
        "0.85",
        "--max-model-len",
        "65536",
        "--max-num-batched-tokens",
        "4096",
        "--max-num-seqs",
        "64",
        "--enable-chunked-prefill",
        "--no-enable-prefix-caching",
        "--use-replayssm",
        "--mamba-backend",
        "flashinfer",
        "--mamba-cache-mode",
        "none",
        "--mm-processor-cache-gb",
        "0",
        "--no-async-scheduling",
        "--limit-mm-per-prompt",
        '{"audio":{"count":1,"length":57600000}}',
        "--speculative-config",
        '{"method":"mtp","num_speculative_tokens":8}',
        "--reasoning-parser",
        "nemotron_v3",
        "--trust-request-mm-kwargs",
        "--middleware",
        "nemo.collections.speechlm2.vllm.salm.ctc_serving.ctc_timestamp_middleware",
    ]
    os.execv(command[0], command)


if __name__ == "__main__":
    main()
