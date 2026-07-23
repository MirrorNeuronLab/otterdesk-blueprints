from domain.intake import frame_goal

from ._shared import create_domain_agent


run = create_domain_agent("research_goal_framer", frame_goal)
