"""Worker binding that owns the long-lived browser bridge service."""

from __future__ import annotations


def run(_context=None) -> dict[str, str]:
    # `main` blocks until the service is deliberately stopped. Uvicorn then
    # returns normally, allowing the finalizer to publish a terminal artifact
    # without replaying any browser command.
    from services.duck_control_service import main

    main()
    return {"service": "microduck-controller", "status": "stopped"}
