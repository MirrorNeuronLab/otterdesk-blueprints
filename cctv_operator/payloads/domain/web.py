"""Read-only co-worker workspace. All controls remain in the authenticated Job MCP."""

import asyncio
from pathlib import Path
import time
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .window_evidence import display_frame


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

    @app.get("/api/observations")
    def observations(view: Literal["all", "goal"], before_id: str = Query(min_length=1, max_length=160),
                     revision: int = 0):
        if view == "goal" and revision != operator.analysis.revision:
            raise HTTPException(409, "The monitoring goal changed.")
        try:
            return operator.store.history(current_run=True, goal_revision=revision if view == "goal" else None,
                                          older_than=before_id)
        except ValueError:
            raise HTTPException(404, "The observation is outside this view.") from None

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

    @app.get("/api/windows/{identity}/snapshot.jpg")
    def window_snapshot(identity: str):
        caption = operator.store.saved(identity) if len(identity) <= 160 else None
        if not caption or not caption.get("snapshot"):
            raise HTTPException(404, "This window has no saved snapshot.")
        jpeg = operator.store.frame(identity)
        return Response(display_frame(jpeg, caption["snapshot"].get("bbox_2d")), media_type="image/jpeg")

    return app
