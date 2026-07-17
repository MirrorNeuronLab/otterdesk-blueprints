from financial_domain import workflow
from ._shared import create_domain_agent

run = create_domain_agent("financial_folder_watcher", workflow.step_financial_folder_watcher)

