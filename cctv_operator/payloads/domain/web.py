"""Read-only co-worker workspace. All controls remain in the authenticated Job MCP."""

import asyncio
from pathlib import Path
import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles


def create_app(operator):
    assets = Path(__file__).resolve().parents[1] / "web_assets"
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.mount("/static", StaticFiles(directory=assets), name="static")

    @app.middleware("http")
    async def private_responses(request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' blob:; style-src 'self'; script-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'none'"
        return response

    @app.get("/")
    async def index():
        return FileResponse(assets / "index.html")

    @app.get("/health")
    async def health():
        if operator.failure:
            raise HTTPException(503, "Video analysis needs attention.")
        return {"status": "ok"}

    @app.get("/api/status")
    async def status():
        return operator.snapshot()

    @app.get("/api/export")
    async def export():
        import json
        return Response(json.dumps(operator.snapshot()), media_type="application/json",
                        headers={"Content-Disposition": 'attachment; filename="cctv-observations.json"'})

    @app.get("/api/preview.mjpeg")
    async def preview(request: Request):
        async def frames():
            previous = -1
            while not await request.is_disconnected():
                if operator.preview.jpeg and operator.preview.frame_number != previous:
                    frame, previous = operator.preview.jpeg, operator.preview.frame_number
                    yield b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " + str(len(frame)).encode() + b"\r\n\r\n" + frame + b"\r\n"
                await asyncio.sleep(0.1)
        return StreamingResponse(frames(), media_type="multipart/x-mixed-replace; boundary=frame")

    @app.get("/api/snapshot.jpg")
    async def snapshot():
        if not operator.preview.jpeg or time.time() - operator.preview.last_frame_at > 8:
            raise HTTPException(503, "No recent preview frame is available.")
        return Response(operator.preview.jpeg, media_type="image/jpeg")

    return app
