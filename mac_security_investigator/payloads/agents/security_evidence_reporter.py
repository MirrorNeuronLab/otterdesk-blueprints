from domain.operations import publish
from ._binding import bind

run = bind(publish)
