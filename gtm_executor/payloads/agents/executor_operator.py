"""Thin marketing specialist binding."""
from domain.service import run_service
def run(context=None, **options):
    return run_service(context, **options)
