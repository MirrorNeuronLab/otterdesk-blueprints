from domain.tax import step_tax_workpaper_preparer
from ._shared import create_domain_agent

run = create_domain_agent("tax_workpaper_preparer", step_tax_workpaper_preparer)

