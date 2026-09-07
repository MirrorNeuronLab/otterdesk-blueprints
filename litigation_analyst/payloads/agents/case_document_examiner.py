from domain.intake import prepare_sources
from ._binding import bind

run = bind(prepare_sources)
