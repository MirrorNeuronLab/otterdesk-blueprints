"""Five-molecule selection policy for the bounded discovery product."""

from typing import Any


def five_distinct_candidates(
    candidates: list[dict[str, Any]], *, synthetic: bool
) -> list[dict[str, Any]]:
    if not synthetic:
        from rdkit import Chem

    unique = {}
    for candidate in candidates:
        smiles = str(candidate.get("smiles") or "")
        if synthetic:
            key = smiles
        else:
            molecule = Chem.MolFromSmiles(smiles)
            if molecule is None:
                continue
            key = Chem.MolToSmiles(molecule, isomericSmiles=True)
        if key:
            unique.setdefault(key, candidate)
    selected = list(unique.values())[:5]
    if len(selected) != 5:
        raise RuntimeError("Discovery requires five distinct valid candidates; generator returned fewer.")
    return selected


def best_screen_per_candidate(screens: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Retain the first (highest-ranked) target for each selected molecule."""
    selected = {}
    for screen in screens:
        selected.setdefault(screen["candidate"]["smiles"], screen)
    if len(selected) != 5:
        raise RuntimeError("Screening did not produce evidence for all five candidates.")
    return list(selected.values())
