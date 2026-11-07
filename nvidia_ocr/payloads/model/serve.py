"""Prepare the CUDA extension on its native model node, then serve OCR."""

from __future__ import annotations

import hashlib
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

MODEL_REVISION = "0e83e83f17943524b90afa6c0fd82ac2bc1a40ca"


def prepare_extension():
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("OCR model preparation requires NVIDIA CUDA")
    major, minor = torch.cuda.get_device_capability()
    if major < 8:
        raise RuntimeError("Nemotron OCR requires NVIDIA Ampere or newer")
    root = Path("/opt/nemotron-ocr/nemotron-ocr")
    target = root / "src/nemotron_ocr_cpp"
    identity = hashlib.sha256(
        f"{MODEL_REVISION}:{torch.__version__}:{torch.version.cuda}:{platform.machine()}:{major}.{minor}".encode()
    ).hexdigest()
    cache = Path("/cache/nemotron-ocr-extensions") / identity
    cached = list(cache.glob("_nemotron_ocr_cpp*.so"))
    if cached:
        for path in cached:
            shutil.copy2(path, target / path.name)
    else:
        subprocess.run(
            [sys.executable, "scripts/build-extension.py"],
            cwd=root,
            check=True,
            timeout=1800,
            env={
                **os.environ,
                "TORCH_CUDA_ARCH_LIST": f"{major}.{minor}",
                "ARCH": platform.machine(),
                "BUILD_CPP_EXTENSION": "1",
            },
        )
        compiled = list(target.glob("_nemotron_ocr_cpp*.so"))
        if not compiled:
            raise RuntimeError("OCR CUDA extension build produced no shared library")
        cache.mkdir(parents=True, exist_ok=True)
        for path in compiled:
            temporary = cache / (path.name + ".tmp")
            shutil.copy2(path, temporary)
            temporary.replace(cache / path.name)
    # The upstream shim imports its shared library relative to this source package.
    sys.path.insert(0, str(root / "src"))


def main():
    prepare_extension()
    from mn_nvidia_ocr_skill.server import main as serve

    serve()


if __name__ == "__main__":
    main()
