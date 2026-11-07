"""Managed, bounded OCR HTTP service. No client paths or remote URLs are accepted."""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request

from .backend import NemotronOcrBackend
from .contracts import MAX_INPUT_BYTES

MAX_REQUEST_BYTES = 4 * ((MAX_INPUT_BYTES + 2) // 3) + 1024


def create_app(*, backend_factory=NemotronOcrBackend):
    gate = asyncio.Lock()

    @asynccontextmanager
    async def lifespan(app):
        # SDK first-use preparation starts this service. Readiness means weights loaded.
        app.state.backend = await asyncio.to_thread(lambda: backend_factory().prepare())
        try:
            yield
        finally:
            app.state.backend = None

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/health")
    def health():
        if getattr(app.state, "backend", None) is None:
            raise HTTPException(503, "OCR model is not ready")
        return {"ready": True}

    @app.post("/v1/ocr")
    async def ocr(request: Request):
        if gate.locked():
            raise HTTPException(429, "OCR model is busy")
        async with gate:
            body = bytearray()
            try:
                async with asyncio.timeout(30):
                    async for chunk in request.stream():
                        if len(body) + len(chunk) > MAX_REQUEST_BYTES:
                            raise HTTPException(
                                413, "OCR document exceeds request limit"
                            )
                        body.extend(chunk)
                payload = json.loads(body)
                if not isinstance(payload, dict) or set(payload) != {
                    "document_base64",
                    "suffix",
                    "merge_level",
                }:
                    raise ValueError("Invalid OCR request")
                encoded = payload["document_base64"]
                if not isinstance(encoded, str):
                    raise TypeError("Invalid OCR encoding")
                data = base64.b64decode(encoded, validate=True)
                return await asyncio.to_thread(
                    app.state.backend.extract,
                    data,
                    suffix=payload["suffix"],
                    merge_level=payload["merge_level"],
                )
            except HTTPException:
                raise
            except TimeoutError:
                raise HTTPException(408, "OCR request read timed out") from None
            except (ValueError, TypeError, KeyError, binascii.Error):
                raise HTTPException(
                    400, "Invalid or unsupported OCR document"
                ) from None
            except Exception:  # noqa: BLE001 - sanitize model and decoder diagnostics
                # Model exceptions may contain document text or filesystem paths.
                raise HTTPException(
                    503, "OCR inference failed; check model readiness"
                ) from None

    return app


def main():
    import uvicorn

    uvicorn.run(create_app(), host="0.0.0.0", port=8000, workers=1, access_log=False)


if __name__ == "__main__":
    main()
