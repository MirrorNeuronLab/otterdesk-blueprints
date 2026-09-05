"""Write a terminal, run-scoped service record after deliberate shutdown."""

from __future__ import annotations


def run(_context=None) -> dict[str, object]:
    from services.duck_control_service import configured_run_dir, write_final_artifact

    artifact = write_final_artifact(configured_run_dir())
    return {"status": "service_stopped", "artifact": artifact}
