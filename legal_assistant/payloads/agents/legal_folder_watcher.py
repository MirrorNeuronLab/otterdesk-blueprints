from legal_domain.operations import watch
from ._shared import create_domain_agent
run = create_domain_agent("legal_folder_watcher", watch)

