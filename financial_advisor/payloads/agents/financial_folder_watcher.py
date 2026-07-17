from financial_domain import legacy
from ._shared import create_domain_agent

run = create_domain_agent("financial_folder_watcher", legacy.step_financial_folder_watcher)

