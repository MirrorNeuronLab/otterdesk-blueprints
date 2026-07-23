from domain.autonomous import autonomous_research

from ._shared import create_domain_agent


run = create_domain_agent("autonomous_researcher", autonomous_research)
