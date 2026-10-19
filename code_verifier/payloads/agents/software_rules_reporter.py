from domain.reporting import publish
from ._binding import bind

run = bind(publish)
