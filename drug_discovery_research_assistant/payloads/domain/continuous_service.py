"""One scientific cycle per run, with explicit interrupted-cycle reconciliation."""
from mn_blueprint_blocks.contracts import BlockError, fingerprint
from mn_sdk.agent_events import report_activity
from service.scripts.continuous_service import run_service, is_fake

from .configuration import BLUEPRINT_ID, cycle_configuration
from .native_stages import read_discovery_state, write_discovery_state


def run_discovery_service(block, inputs):
    block.check()
    report_activity("Discovering five candidates", owner_blueprint=BLUEPRINT_ID, run_dir=block.store.run_dir)
    state = read_discovery_state(block, inputs)
    config = cycle_configuration(block, state)
    started = block.store.path("discovery/cycle-started.json")
    existed = started.exists()
    block.store.commit("discovery/cycle-started.json", {"configuration": fingerprint(config),
        "source": inputs["previous"]["state"]}, kind="discovery_cycle_start")
    if existed:
        status = block.store.read_path("service_state.json") if block.store.path("service_state.json").is_file() else {}
        if status.get("status") != "stopped" or status.get("completed_cycles") != 1:
            raise BlockError("outcome_unknown", "Inspect the interrupted scientific cycle before starting another run.")
    else:
        block.check()
        status = run_service(config, block.store.run_dir, check=block.check)
    reports = status.get("reports") or []
    if status.get("completed_cycles") != 1 or len(reports) != 1:
        raise ValueError("Discovery did not complete its required single scientific cycle.")
    report = block.store.read_path("cycles/cycle-000000/cycle_report.json")
    if report != reports[0] or report.get("cycle_id") != 0 or report.get("mode") != (
            "fake_smoke_test" if is_fake(config) else "live"):
        raise BlockError("outcome_unknown", "The completed cycle evidence does not match the scientific status.")
    paths = ["cycles/cycle-000000/" + name for name in ["generated_candidates.json", "folding_results.json",
        "drugclip_screening.json", "simulation_results.json", "cycle_report.json"]]
    state["cycle_artifacts"] = [block.store.commit_bytes(path, block.store.path(path).read_bytes(),
        kind="scientific_cycle").to_dict() for path in paths]
    state["service_reports"] = reports
    return {"completed_cycles": 1, "service_status": status.get("status"),
            "state": write_discovery_state(block, state, "cycle")}
