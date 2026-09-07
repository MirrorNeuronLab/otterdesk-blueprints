from domain.reporting import publish_review
from ._binding import bind

run = bind(publish_review)
