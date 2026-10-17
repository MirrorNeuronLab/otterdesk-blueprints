"""Publication, retirement, and test source authority are explicit contracts."""

import json

import pytest

import blueprint_modernization_support as support
from mn_sdk.blueprints import read_catalog


RETIRED = (
    "legal_assistant", "purchasing_manager", "gtm_assistant", "gtm_ai_workflow",
    "bibblio_profitability_workforce", "bibblio_gtm_coworker",
    "bibblio_finance_coworker", "bibblio_learning_safety_coworker",
    "bibblio_content_studio_coworker", "bibblio_parent_lifecycle_coworker",
)


@pytest.mark.parametrize("blueprint_id", RETIRED)
def test_retired_products_have_no_catalog_entry_or_executable_package(blueprint_id):
    entries = read_catalog(support.ROOT / "index.json")
    assert blueprint_id not in {entry["id"] for entry in entries}
    assert blueprint_id not in {entry["path"] for entry in entries}
    assert not (support.ROOT / blueprint_id).exists()


@pytest.mark.parametrize("blueprint_id", ["gtm_planner", "gtm_executor"])
def test_local_marketing_packages_remain_unpublished(blueprint_id):
    inventory = json.loads((support.ROOT / "index.json").read_text())
    assert blueprint_id not in inventory
    assert (support.ROOT / blueprint_id / "manifest.json").is_file()


def test_test_subject_resolution_never_borrows_a_sibling_product(monkeypatch, tmp_path):
    catalog = tmp_path / "catalog"
    sibling = tmp_path / "workspace" / "mn-blueprints" / "retired-product"
    sibling.mkdir(parents=True)
    (sibling / "manifest.json").write_text("{}")
    monkeypatch.setattr(support, "ROOT", catalog)
    monkeypatch.setattr(support, "WORKSPACE", sibling.parents[1])
    assert support.blueprint_path("retired-product") == catalog / "retired-product"
    with pytest.raises(ValueError, match="does not exist"):
        support.source_manifest("retired-product")
