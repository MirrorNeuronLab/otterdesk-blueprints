from domain.intake import step_financial_folder_watcher
from ._shared import create_domain_agent

run = create_domain_agent("financial_folder_watcher", step_financial_folder_watcher)

