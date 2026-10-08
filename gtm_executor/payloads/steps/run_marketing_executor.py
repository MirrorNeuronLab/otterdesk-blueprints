"""Logical service boundary; domain work belongs to the specialist."""
from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output, run_input
STEP = StepSpec(input=InputSpec(fields={k: run_input(k) for k in ['website_url', 'goal_id', 'peer_job_id', 'collaboration_group_id', 'collaboration_peers', 'instruction', 'common_goal', 'output_folder', 'contacts_file', 'inbox_id', 'newsletter_eligible']}), flow=agent('executor_operator'), output=OutputSpec(fields={"status": flow_output()}))
