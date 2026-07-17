from drug_discovery_domain.operations import evaluate_binding
from ._shared import create_domain_agent
run = create_domain_agent("binding_evaluation", evaluate_binding)

