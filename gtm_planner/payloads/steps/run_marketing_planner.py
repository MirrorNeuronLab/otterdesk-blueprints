"""Logical service boundary; domain work belongs to the specialist."""
from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output, run_input
STEP = StepSpec(input=InputSpec(fields={k: run_input(k) for k in ['website_url', 'goal_id', 'peer_job_id', 'instruction', 'common_goal', 'output_folder']}), flow=agent('planner_operator'), output=OutputSpec(fields={"status": flow_output()}))
