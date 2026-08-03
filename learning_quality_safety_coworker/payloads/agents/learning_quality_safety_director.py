from domain.workers import run_learning_safety_director

from ._shared import create_domain_agent


run = create_domain_agent("bibblio_learning_safety_director", run_learning_safety_director)

