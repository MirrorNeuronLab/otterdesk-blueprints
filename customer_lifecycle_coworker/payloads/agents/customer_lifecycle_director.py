from domain.workers import run_customer_lifecycle_director

from ._shared import create_domain_agent


run = create_domain_agent("customer_lifecycle_director", run_customer_lifecycle_director)

