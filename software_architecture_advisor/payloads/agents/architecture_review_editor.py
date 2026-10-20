from domain.investigation_block import publish
from ._binding import bind

run = bind(publish, step_input=True)
