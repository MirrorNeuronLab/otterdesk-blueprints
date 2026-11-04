"""Own the streaming task, read-only workspace and internal MCP listeners."""

import asyncio
import fcntl
from pathlib import Path
import socket
import threading

import uvicorn

from .analysis import Analysis
from .caption_store import CaptionStore
from .preview import Preview
from .publication import Publisher
from .realtime_client import VLMClient, safe_error
from .settings import camera_settings, service_url
from .web import create_app


def listener(host, port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((host, port))
        sock.listen(128)
        sock.setblocking(False)
        return sock
    except BaseException:
        sock.close()
        raise


class Operator:
    def __init__(self, *, config, job_id, run_id, job_data_dir, run_dir, host, port, mcp_port):
        self.config, self.job_id, self.run_id = config, job_id, run_id
        self.settings = camera_settings(config)
        self.base_url = service_url(config["vlm"]["base_url"])
        self.failure, self.phase = None, "starting"
        self.run_dir = Path(run_dir)
        state_dir = Path(job_data_dir) / "state" / "realtime_vlm"
        state_dir.mkdir(parents=True, exist_ok=True)
        self.ownership = (state_dir / "operator.lock").open("a")
        try:
            fcntl.flock(self.ownership, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.ownership.close()
            raise RuntimeError("This Job already has a camera operator.") from None
        self.web_socket = self.mcp_socket = None
        self.thread = None
        self.loop = None
        self.started = threading.Event()
        try:
            from mn_sdk_mcp.cli import default_host
            self.store = CaptionStore(state_dir / "captions.sqlite3", job_id=job_id, run_id=run_id,
                                      source_id=self.settings.source_id,
                                      max_records=config.get("retention", {}).get("max_captions", 10000))
            from mn_sdk_mcp import JobExchangeStore
            self.exchange = JobExchangeStore(self.run_dir / "operator_activity.sqlite3", allowed_root=self.run_dir,
                                             job_id=job_id, blueprint_id="cctv_operator", run_id=run_id)
            self.publisher = Publisher(self.run_dir, self.store, self.exchange)
            self.preview = Preview()
            self.web_socket = listener(host, port)
            # Core's published internal range forwards to its container interface.
            # The SDK keeps native execution on loopback and honors that proxy.
            self.mcp_socket = listener(default_host(), mcp_port)
        except BaseException:
            self.close_sockets()
            self.ownership.close()
            raise

    def snapshot(self):
        result = self.analysis.snapshot() if hasattr(self, "analysis") else {"session": {"status": "starting"}, "captions": []}
        return {**result, "preview": self.preview.status(), "phase": self.phase, "error": self.failure,
                "service": "NVIDIA vss-rt-vlm", "camera": self.settings.name,
                "limitation": "Sampled video descriptions require human review. The live preview is separate from analyzed windows."}

    def start(self):
        self.thread = threading.Thread(target=self._thread_main, name="cctv-operator", daemon=True)
        self.thread.start()
        if not self.started.wait(10):
            raise RuntimeError("The camera operator did not initialize.")
        if self.failure:
            raise RuntimeError(self.failure)

    def _thread_main(self):
        try:
            asyncio.run(self._main())
        except Exception as error:
            self.failure = safe_error(error)
            self.phase = "error"
        finally:
            self.started.set()

    async def _capture(self):
        try:
            async with asyncio.timeout(self.config.get("vlm", {}).get("startup_timeout_seconds", 600)):
                while True:
                    try:
                        await self.client.model()
                        break
                    except Exception:
                        await asyncio.sleep(2)
            await self.analysis.start()
            self.phase = "running"
            while not self.shutdown.is_set():
                # Goal changes replace the task under the same serial lock.
                # The original task ending is not a failure of its replacement.
                if self.analysis.task.done() and not self.analysis.lock.locked():
                    self.failure = self.analysis.state.get("error") or "The live analysis stopped unexpectedly. Try again."
                    self.phase = "error"
                    return
                await asyncio.sleep(.1)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            self.failure = safe_error(error)
            self.analysis.update(status="error", error=self.failure)
            self.phase = "error"

    async def _main(self):
        from .mcp_tools import create_operator_mcp_server
        self.loop = asyncio.get_running_loop()
        self.shutdown = asyncio.Event()
        self.client = VLMClient(self.base_url)
        self.analysis = Analysis(self.client, self.settings, self.store, self.publisher.caption, self.publisher.status)
        self.analysis.configured_prompt = self.settings.prompt
        mcp = create_operator_mcp_server(self)
        options = dict(getattr(mcp, "_mn_http_options", {}))
        options.pop("port", None)
        from starlette.responses import JSONResponse
        from starlette.routing import Route
        mcp_app = mcp.streamable_http_app(**options)
        async def control_health(request):
            return JSONResponse({"status": "ok"})
        mcp_app.router.routes.append(Route("/health", control_health))
        self.web_server = uvicorn.Server(uvicorn.Config(create_app(self), log_level="warning", access_log=False,
                                                        timeout_graceful_shutdown=2))
        self.mcp_server = uvicorn.Server(uvicorn.Config(mcp_app, log_level="warning",
                                                        access_log=False, timeout_graceful_shutdown=2))
        web = self.web_task = asyncio.create_task(self.web_server.serve(sockets=[self.web_socket]))
        controls = self.mcp_task = asyncio.create_task(self.mcp_server.serve(sockets=[self.mcp_socket]))
        capture = None
        errors = []
        try:
            await asyncio.to_thread(self.preview.start, self.settings.uri)
            capture = asyncio.create_task(self._capture())
            self.started.set()
            await self.shutdown.wait()
        finally:
            self.phase = "stopping"
            if capture:
                capture.cancel()
                await asyncio.gather(capture, return_exceptions=True)
            for operation in (self.analysis.close, self.client.http.aclose):
                try:
                    await operation()
                except Exception as error:
                    errors.append(error)
            try:
                await asyncio.to_thread(self.preview.stop)
            except Exception as error:
                errors.append(error)
            self.web_server.should_exit = self.mcp_server.should_exit = True
            await asyncio.gather(web, controls, return_exceptions=True)
            self.phase = "error" if self.failure or errors else "stopped"
            if errors:
                self.failure = "Couldn't release all camera resources. Check NVIDIA before starting again."

    def healthy(self):
        return (self.thread is not None and self.thread.is_alive() and self.failure is None
                and getattr(self, "web_server", None) is not None
                and self.web_server.started and self.mcp_server.started
                and not self.web_task.done() and not self.mcp_task.done())

    def stop(self):
        try:
            if self.loop and self.loop.is_running():
                self.loop.call_soon_threadsafe(self.shutdown.set)
            if self.thread:
                self.thread.join(timeout=90)
                if self.thread.is_alive():
                    raise RuntimeError("The camera operator did not stop before its cleanup deadline.")
            if self.store.state("active_request"):
                raise RuntimeError("The NVIDIA camera request still needs cleanup.")
        finally:
            if not self.thread or not self.thread.is_alive():
                self.close_sockets()
                self.ownership.close()

    def close_sockets(self):
        for sock in (self.web_socket, self.mcp_socket):
            if sock:
                sock.close()
