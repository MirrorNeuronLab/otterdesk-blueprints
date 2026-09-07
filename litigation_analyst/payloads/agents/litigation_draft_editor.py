from domain.reporting import write_review
from ._binding import bind

run = bind(write_review)
