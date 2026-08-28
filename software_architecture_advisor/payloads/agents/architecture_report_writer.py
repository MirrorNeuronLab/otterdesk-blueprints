from domain.report_drafting import draft_architecture_report

from ._shared import create_domain_agent

run = create_domain_agent("architecture_report_writer", draft_architecture_report)
