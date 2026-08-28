from domain.native_stages import discover_targets

from ._shared import create_domain_agent


run = create_domain_agent("target_biology_researcher", discover_targets)
