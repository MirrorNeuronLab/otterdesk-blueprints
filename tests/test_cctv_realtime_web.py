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
