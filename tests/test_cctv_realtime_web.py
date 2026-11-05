"""Read-only HTTP and safe state projection without a live camera."""

from types import SimpleNamespace

from fastapi.testclient import TestClient

from cctv_operator.payloads.domain.web import create_app


def test_workspace_never_exposes_mutating_camera_endpoints_or_private_configuration():
    state = {"session": {"status": "starting"}, "captions": [], "phase": "starting",
             "error": None, "camera": "Camera", "preview": {"connected": False},
             "limitation": "Sampled video descriptions."}
    operator = SimpleNamespace(failure=None, snapshot=lambda: state,
                               preview=SimpleNamespace(jpeg=None, last_frame_at=0))
    with TestClient(create_app(operator)) as client:
        assert client.get("/").status_code == 200
        response = client.get("/api/status")
        assert response.json() == state
        assert response.headers["cache-control"] == "no-store"
        assert "script-src 'self'" in response.headers["content-security-policy"]
        assert client.get("/api/snapshot.jpg").status_code == 503
        for endpoint in ["/api/analysis/start", "/api/analysis/stop", "/api/preview", "/api/goal"]:
            assert client.post(endpoint, json={"uri": "rtsp://private:credential@camera/stream"}).status_code == 404
        export = client.get("/api/export")
        assert export.json() == state
        assert "attachment" in export.headers["content-disposition"]
        assert client.get("/health").status_code == 200
        operator.failure = "The NVIDIA service disconnected."
        assert client.get("/health").status_code == 503


def test_workspace_pages_and_snapshots_stay_in_the_selected_run_and_goal(tmp_path):
    from datetime import datetime, timedelta, timezone
    from cctv_operator.payloads.domain.caption_store import CaptionStore
    from test_cctv_realtime_history import save

    store = CaptionStore(tmp_path / "captions.db", job_id="job", source_id="camera", run_id="previous")
    start = datetime.now(timezone.utc)
    save(store, "previous-run", start, "red")
    active = CaptionStore(store.path, job_id="job", source_id="camera", run_id="current")
    save(active, "earlier", start, "red")
    save(active, "later", start + timedelta(seconds=4), "blue")
    with TestClient(create_app(SimpleNamespace(store=active, analysis=SimpleNamespace(revision=2)))) as client:
        result = client.get("/api/observations", params={"view":"all", "before_id":"later"})
        assert [row["id"] for row in result.json()["observations"]] == ["earlier"]
        assert client.get("/api/observations", params={"view":"goal","revision":1,"before_id":"later"}).status_code == 409
        assert client.get("/api/observations", params={"view":"all","before_id":"previous-run"}).status_code == 404
        assert client.get("/api/windows/previous-run/snapshot.jpg").status_code == 404
        assert client.get("/api/windows/earlier/snapshot.jpg").content == active.frame("earlier")


def test_saved_frame_highlight_is_rendered_without_mutating_original_bytes(tmp_path):
    import io
    from datetime import datetime, timezone
    from PIL import Image
    from cctv_operator.payloads.domain.caption_store import CaptionStore
    from test_cctv_realtime_history import save

    store = CaptionStore(tmp_path / "captions.db", job_id="job", source_id="camera", run_id="run")
    account = save(store, "highlight", datetime.now(timezone.utc), "red")
    original = store.frame("highlight")
    account["snapshot"]["bbox_2d"] = [200, 200, 700, 800]
    with TestClient(create_app(SimpleNamespace(store=SimpleNamespace(saved=lambda _: account, frame=lambda _: original)))) as client:
        response = client.get("/api/windows/highlight/snapshot.jpg")
        assert response.headers["content-type"] == "image/jpeg"
        with Image.open(io.BytesIO(response.content)) as highlighted, Image.open(io.BytesIO(original)) as source:
            assert highlighted.size == source.size
            r, g, b = highlighted.getpixel((45, 45))
            assert r > 170 and g > 150 and r - b > 50 and g - b > 30
        assert store.frame("highlight") == original
