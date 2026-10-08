"""Explicitly prepared, resident MobileCLIP2 image/text embeddings.

Importing this module performs no downloads or model initialization. The optional
backend stays in the process which owns it; callers never reload it per frame.
"""

from __future__ import annotations

import io
from collections import OrderedDict
from pathlib import Path

from mn_sdk_models.embeddings import unit_vector

MODEL_ID = "apple/MobileCLIP2-S0"
MODEL_REVISION = "3136ea51c8ed56b9f9abfab04cb816735aaad6cb"
CHECKPOINT = "mobileclip2_s0.pt"
PREPARED_DIRECTORY = Path("/opt/mn-models/mobileclip")


def prepare_mobileclip(directory: str | Path) -> Path:
    """Download the pinned Apple artifact during explicit dependency preparation."""
    from huggingface_hub import hf_hub_download

    return Path(hf_hub_download(
        repo_id=MODEL_ID, filename=CHECKPOINT, revision=MODEL_REVISION,
        local_dir=str(directory),
    ))


class MobileCLIPEncoder:
    """One CUDA encoder with bounded text caching; no implicit CPU fallback."""

    def __init__(self, checkpoint: str | Path = PREPARED_DIRECTORY / CHECKPOINT):
        self.checkpoint = Path(checkpoint)
        self._backend = None
        self._texts = OrderedDict()

    def _load(self):
        if self._backend is None:
            if not self.checkpoint.is_file():
                raise RuntimeError("MobileCLIP checkpoint was not prepared")
            import open_clip
            import torch
            from timm.utils.model import reparameterize_model

            if not torch.cuda.is_available():
                raise RuntimeError("MobileCLIP requires the declared CUDA worker")
            model, _, preprocess = open_clip.create_model_and_transforms(
                "MobileCLIP2-S0", pretrained=str(self.checkpoint),
                image_mean=(0, 0, 0), image_std=(1, 1, 1), weights_only=True,
            )
            model.eval()
            model = reparameterize_model(model, inplace=True).to("cuda")
            self._backend = (torch, model, preprocess, open_clip.get_tokenizer("MobileCLIP2-S0"))
        return self._backend

    def encode_image(self, jpeg: bytes) -> list[float]:
        if not isinstance(jpeg, bytes) or not 0 < len(jpeg) <= 2_097_152:
            raise ValueError("image must contain at most 2 MiB")
        from PIL import Image, ImageOps

        torch, model, preprocess, _ = self._load()
        with Image.open(io.BytesIO(jpeg)) as image:
            if image.format != "JPEG" or image.width * image.height > 8_000_000:
                raise ValueError("image must be a bounded JPEG")
            # Preserve the full field of view before the model's square crop.
            # Otherwise wide-frame evidence near either edge disappears.
            prepared_image = ImageOps.pad(image.convert("RGB"), (256, 256), color=(0, 0, 0))
            prepared = preprocess(prepared_image).unsqueeze(0).to("cuda")
        with torch.inference_mode():
            vector = model.encode_image(prepared).float().cpu()[0].tolist()
        return unit_vector(vector)

    def encode_text(self, text: str) -> list[float]:
        if not isinstance(text, str) or not text.strip() or len(text) > 1000:
            raise ValueError("text must contain 1 to 1000 characters")
        if text in self._texts:
            self._texts.move_to_end(text)
            return list(self._texts[text])
        torch, model, _, tokenizer = self._load()
        with torch.inference_mode():
            vector = model.encode_text(tokenizer([text]).to("cuda")).float().cpu()[0].tolist()
        result = unit_vector(vector)
        self._texts[text] = result
        if len(self._texts) > 64:
            self._texts.popitem(last=False)
        return list(result)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare", required=True, nargs="?", type=Path, const=PREPARED_DIRECTORY)
    args = parser.parse_args()
    prepare_mobileclip(args.prepare)
