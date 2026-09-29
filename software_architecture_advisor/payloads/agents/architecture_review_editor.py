from domain.catalog_publication import publish
from ._binding import bind

run = bind(publish)
