"""Pinned, offline RF-DETR inference adapter for CCTV person events."""

import argparse
import hashlib
import importlib.metadata
import io
import json
import time
import urllib.request
from pathlib import Path


PACKAGE_VERSION = "1.11.2"
MODEL_ROOT = Path("/opt/mn-models/rfdetr")
MODELS = {
    "small": {"class": "RFDETRSmall", "resolution": 512,
              "sha256": "d81979a9213a2109345158ce9232668df4c1ae52e9b8db3f2ec0a8cbad959b33"},
    "medium": {"class": "RFDETRMedium", "resolution": 576,
               "sha256": "749ff6071828aaffac63e204c4f4135ed3d6cdae4d702e086c360edc3b5768c8"},
}


def checkpoint_path(size, root=MODEL_ROOT):
    if size not in MODELS:
        raise ValueError("person_detector.model must be small or medium")
    return Path(root) / f"rf-detr-{size}.pth"


def verify_checkpoint(size, root=MODEL_ROOT):
    path = checkpoint_path(size, root)
    if not path.is_file():
        raise FileNotFoundError("RF-DETR checkpoint is missing; rebuild the CCTV worker image")
    with path.open("rb") as handle:
        digest = hashlib.file_digest(handle, "sha256").hexdigest()
    if digest != MODELS[size]["sha256"]:
        raise ValueError("RF-DETR checkpoint hash differs from the pinned model")
    return path


def prepare_models(root=MODEL_ROOT):
    """Build-only downloads; runtime construction never invokes this function."""
    Path(root).mkdir(parents=True, exist_ok=True)
    for size in MODELS:
        target = checkpoint_path(size, root)
        temporary = target.with_suffix(".download")
        try:
            with urllib.request.urlopen(
                f"https://storage.googleapis.com/rfdetr/{size}_coco/checkpoint_best_regular.pth",
                timeout=120,
            ) as response, temporary.open("wb") as handle:
                while block := response.read(1024 * 1024):
                    handle.write(block)
            with temporary.open("rb") as handle:
                if hashlib.file_digest(handle, "sha256").hexdigest() != MODELS[size]["sha256"]:
                    raise ValueError("downloaded RF-DETR checkpoint failed SHA-256 validation")
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)


def load_coco_weights(model, path):
    import torch
    with torch.serialization.safe_globals([argparse.Namespace]):
        checkpoint = torch.load(path, map_location="cpu", weights_only=True)
    state = checkpoint["model"]
    # RF-DETR 1.11 adds this deterministic schema buffer to detection models.
    # Official Small/Medium COCO checkpoints predate it. These models have no
    # keypoints: supply the required empty buffer, then strictly load every
    # learned tensor. Never use strict=False to accept partial/random weights.
    schema = model.model.model._kp_active_mask
    if schema.numel() != 0 or "_kp_active_mask" in state:
        raise ValueError("pinned RF-DETR COCO detection schema differs from the adapter")
    state["_kp_active_mask"] = schema
    model.model.model.load_state_dict(state, strict=True)


class RFDETRPersonDetector:
    def __init__(self, settings=None, *, benchmarks=None, root=MODEL_ROOT):
        settings = settings or {}
        self.size = str(settings.get("model", "small"))
        checkpoint_path(self.size, root)
        self.threshold = float(settings.get("confidence_threshold", .55))
        if not 0 < self.threshold <= 1:
            raise ValueError("person confidence threshold must be in (0,1]")
        self.root, self.benchmarks = root, benchmarks
        self.variant = f"RF-DETR {self.size.title()} / rfdetr {PACKAGE_VERSION} / PyTorch FP16"
        self.model = None
        self.metadata = {"package": f"rfdetr=={PACKAGE_VERSION}", "resolution": MODELS[self.size]["resolution"],
                         "weights_sha256": MODELS[self.size]["sha256"], "threshold": self.threshold}
        self.calls = 0

    def load(self):
        if self.model is not None:
            return
        start = time.perf_counter()
        status = "ok"
        try:
            path = verify_checkpoint(self.size, self.root)
            import torch
            import rfdetr
            if importlib.metadata.version("rfdetr") != PACKAGE_VERSION:
                raise RuntimeError("RF-DETR package differs from the worker contract")
            if not torch.cuda.is_available():
                raise RuntimeError("RF-DETR person events require CUDA")
            self.metadata.update(device=torch.cuda.get_device_name(0), cuda=torch.version.cuda, torch=torch.__version__)
            # Construct the published architecture without its auto-downloader.
            # Load the exact COCO tensors strictly; no network repair or partial
            # random weights are permitted at runtime.
            model = getattr(rfdetr, MODELS[self.size]["class"])(pretrain_weights=None, device="cuda")
            load_coco_weights(model, path)
            model.inference(compile=False, dtype=torch.float16, inplace=True)
            torch.cuda.synchronize()
            self.model = model
        except BaseException:
            status = "error"
            raise
        finally:
            if self.benchmarks:
                self.benchmarks.record("person.model_load", (time.perf_counter() - start) * 1000,
                    variant=self.variant, phase="cold", status=status, metadata=self.metadata)

    def detect(self, jpeg):
        self.load()
        from PIL import Image
        import torch
        phase = "cold" if self.calls == 0 else "warm"
        start = time.perf_counter()
        image = Image.open(io.BytesIO(jpeg)).convert("RGB")
        if self.benchmarks:
            self.benchmarks.record("person.preprocess", (time.perf_counter() - start) * 1000,
                                   variant=self.variant, phase=phase, metadata=self.metadata)
        torch.cuda.synchronize()
        start = time.perf_counter()
        status = "ok"
        try:
            # predict includes RF-DETR's full-view resize, GPU forward and
            # postprocessing. Its internal preprocessing is included in timing.
            result = self.model.predict(image, threshold=self.threshold, include_source_image=False)
            people = [{"label": "person", "confidence": float(score),
                       "xyxy": [float(v) for v in box]} for box, score, name in
                      zip(result.xyxy, result.confidence, result.data["class_name"])
                      if str(name).casefold() == "person"]
            return people
        except BaseException:
            status = "error"
            raise
        finally:
            torch.cuda.synchronize()
            self.calls += 1
            if self.benchmarks:
                self.benchmarks.record("person.inference", (time.perf_counter() - start) * 1000,
                    variant=self.variant, phase=phase, status=status,
                    metadata={**self.metadata, "frames": 1, "peak_gpu_bytes": torch.cuda.max_memory_allocated()})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare", action="store_true", required=True)
    parser.add_argument("--root", type=Path, default=MODEL_ROOT)
    args = parser.parse_args()
    prepare_models(args.root)
    print(json.dumps({"prepared": list(MODELS), "package": PACKAGE_VERSION}))
