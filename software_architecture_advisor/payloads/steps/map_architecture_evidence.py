from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output

from ._shared import inputs

STEP = StepSpec(input=InputSpec(fields=inputs("resolve_software_source")), flow=agent("codebase_mapper"), output=OutputSpec(fields={"architecture_evidence": flow_output()}))
