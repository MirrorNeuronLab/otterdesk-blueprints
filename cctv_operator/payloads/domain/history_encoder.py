"""EmbeddingGemma 2 provider for Membrane's text and original-media unit contracts."""

import io
import threading

from mn_context_engine_sdk.embeddings import normalize_vector
from PIL import Image


class CameraEmbeddings:
    model_id = "google/embeddinggemma-2"
    revision = "914f7f89142e33e77833254d9c9b90c3cef7303b"

    def __init__(self):
        identity = f"{self.model_id}@{self.revision}"
        self.metadata = {"model": identity + ":retrieval-v1", "tokenizer": identity, "dimensions": 768}
        self.encoder = None
        self.lock = threading.Lock()

    def _encode(self, inputs, *, prompt=None):
        with self.lock:
            if self.encoder is None:
                import torch
                from sentence_transformers import SentenceTransformer
                torch.set_num_threads(min(torch.get_num_threads(), 4))
                self.encoder = SentenceTransformer(self.model_id, revision=self.revision, device="cpu",
                    model_kwargs={"dtype": torch.float32}, config_kwargs={"audio_config": None})
            vectors = self.encoder.encode(inputs, prompt_name=prompt, normalize_embeddings=True,
                                          show_progress_bar=False)
        result = [normalize_vector(row.tolist()) for row in vectors]
        if any(len(vector) != 768 for vector in result):
            raise ValueError("Unexpected camera embedding dimensions.")
        return result

    def _result(self, vector):
        return {"vector": vector, "model": self.metadata["model"], "tokenizer": self.metadata["tokenizer"]}

    def embed(self, chunks):
        vectors = []
        for chunk in chunks:
            offset = chunk["start_byte"]
            pieces = [chunk["text"][i:i + 256] for i in range(0, len(chunk["text"]), 256)]
            for piece, vector in zip(pieces, self._encode(pieces, prompt="Retrieval-document"), strict=True):
                end = offset + len(piece.encode())
                vectors.append({"source_id": chunk["source_id"], "revision": chunk["revision"],
                                "start_byte": offset, "end_byte": end, "values": vector})
                offset = end
        return {"vectors": vectors}

    def embed_media(self, media):
        if media.mime_type != "image/jpeg":
            raise ValueError("Camera history requires JPEG images.")
        with Image.open(io.BytesIO(media.data)) as frame:
            vector, = self._encode([{"image": frame.convert("RGB")}])
        return self._result(vector)

    def embed_query(self, text):
        # Bound tokenization without silently truncating long supervisor questions.
        pieces = [text[i:i + 256] for i in range(0, len(text), 256)]
        vectors = self._encode(pieces, prompt="Retrieval-query")
        combined = [sum(v * len(p) for v, p in zip(values, pieces)) for values in zip(*vectors)]
        return self._result(normalize_vector(combined))
