from domain.prompts import author_prompts

from ._shared import create_domain_agent

run = create_domain_agent("improvement_prompt_author", author_prompts)
