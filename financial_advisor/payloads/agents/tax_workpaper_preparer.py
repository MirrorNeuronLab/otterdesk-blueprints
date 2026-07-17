from financial_domain import legacy
from ._shared import create_domain_agent

run = create_domain_agent("tax_workpaper_preparer", legacy.step_tax_workpaper_preparer)

