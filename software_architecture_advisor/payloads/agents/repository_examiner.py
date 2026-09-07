from domain.intake import capture_input
from ._binding import bind

run = bind(capture_input)
