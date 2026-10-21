"""Record a completed Compose shutdown without issuing robot commands."""
from mn_sdk.agent_events import report_activity


def record_stop(block, inputs):
    artifact = {"schema_version": "mn.turtlebot.service_result.v1", "status": "stopped", "service": "turtlebot-warehouse"}
    reference = block.store.commit("final_artifact.json", artifact, kind="service_result")
    report_activity("Warehouse navigation service stopped", kind="result", owner_blueprint="ros_amr_controller", step_id=block.step_id, run_dir=block.store.run_dir)
    return {**artifact, "artifact": reference.to_dict()}
