from domain.conversation import run_conversation_assistant

from ._shared import create_domain_agent


run = create_domain_agent(
    "otterdesk_conversation_assistant",
    run_conversation_assistant,
)

