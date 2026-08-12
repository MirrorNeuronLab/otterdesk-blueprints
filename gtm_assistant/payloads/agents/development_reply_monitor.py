from domain.reply_monitoring import monitor_development_email_replies

from ._shared import create_domain_agent


run = create_domain_agent("development_reply_monitor", monitor_development_email_replies)
