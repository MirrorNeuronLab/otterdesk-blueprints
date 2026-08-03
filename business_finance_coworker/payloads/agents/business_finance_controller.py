from domain.workers import run_finance_controller

from ._shared import create_domain_agent


run = create_domain_agent("bibblio_finance_controller", run_finance_controller)

