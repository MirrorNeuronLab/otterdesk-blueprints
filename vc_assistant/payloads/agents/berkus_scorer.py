"""Berkus valuation worker registered as ``berkus_scorer``."""

from .valuation_scorer import create_valuation_scorer


run = create_valuation_scorer()
