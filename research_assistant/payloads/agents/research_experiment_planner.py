from domain.preflight import assess_experiment_readiness

from ._shared import create_domain_agent


run = create_domain_agent("research_experiment_planner", assess_experiment_readiness)
