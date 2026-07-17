from financial_domain import workflow
from ._shared import create_domain_agent

run = create_domain_agent("tax_workpaper_preparer", workflow.step_tax_workpaper_preparer)

