"""Bill Payne scorecard worker registered as ``scorecard_bill_payne_scorer``."""

from .valuation_scorer import create_valuation_scorer


run = create_valuation_scorer()
