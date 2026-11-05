"""Reviewed OtterDesk package behavior and SDK/CLI/API transport contracts."""

from __future__ import annotations
import hashlib
import json
import shutil
from pathlib import Path
import pytest
from mn_sdk.blueprints import (
    compile_blueprint,
    export_blueprint,
    open_blueprint,
    read_blueprint,
    read_catalog,
)
from catalog_transport_support import (
    reviewed_block_manifest,
    digest,
    configuration_digest,
    configuration_leaves,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).parent / "fixtures/catalog_transport_v1.json"
BASELINE_DOCUMENT = json.loads(FIXTURE.read_text())
BASELINE = BASELINE_DOCUMENT["packages"]


def package_root(record):
    assert record["repository"] == "otterdesk-blueprints"
    return ROOT / record.get("path", record["id"])


@pytest.mark.parametrize(
    "record", BASELINE, ids=lambda row: f"{row['repository']}/{row['path']}"
)
def test_migrated_behavior_and_transport_parity(record, tmp_path):
    from mn_api.blueprints import local_blueprint_from_path
    from mn_cli.libs.blueprint_cmds import _load_blueprint_manifest
    from mn_sdk.blueprints.definition import blueprint_definition

    root = package_root(record)
    package = read_blueprint(root)
    assert package.manifest["id"] == record["id"]
    compiled = compile_blueprint(package)
    assert (
        BASELINE_DOCUMENT["block_identity_policy"]
        == "content-and-current-installed-versions-v1"
    )
    manifest = reviewed_block_manifest(compiled.manifest)
    for name, expected in record["fields"].items():
        actual = manifest.get(name)
        if name == "runtime_without_inputs":
            actual = {
                key: value
                for key, value in manifest.get("runtime", {}).items()
                if key != "initial_inputs"
            }
        elif name == "authored_dependencies":
            actual = package.document("dependencies")
        elif name == "context_profile":
            metadata = manifest.get("metadata", {})
            actual = {
                key: metadata[key]
                for key in ("text_memory", "required_cluster_capabilities")
                if key in metadata
            }
        elif name == "block_contracts":
            metadata = manifest.get("metadata", {})
            actual = {
                key: metadata[key]
                for key in ("mn_blocks", "mn_blocks_lock")
                if key in metadata
            }
        assert digest(actual) == expected, (
            f"{record['id']}: changed reviewed compiled {name}"
        )
    assert (
        configuration_leaves(compiled.configuration.data).keys()
        == record["configuration_leaves"].keys()
    ), f"{record['id']}: added or removed resolved configuration keys"
    for pointer, expected in record["configuration_leaves"].items():
        value = compiled.configuration.data
        for part in pointer.strip("/").split("/") if pointer else []:
            value = value[part.replace("~1", "/").replace("~0", "~")]
        assert configuration_digest(value) == expected, (
            f"{record['id']}: changed resolved configuration {pointer}"
        )
    contracts = package.document("contracts")
    assert contracts.get("outputs", {}) == record["output_contract"]
    if "artifact_contract" in record:
        expected = record["artifact_contract"]
        assert contracts.get("artifacts") == (
            {"schema": expected} if isinstance(expected, str) else expected
        )
    assert _load_blueprint_manifest(root, record["id"]) == blueprint_definition(package)
    _, api_record = local_blueprint_from_path(str(root))
    assert api_record["id"] == package.manifest["id"]
    moved = tmp_path / "relocated" / "package"
    shutil.copytree(
        root,
        moved,
        ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", ".venv"),
    )
    assert compile_blueprint(read_blueprint(moved)).fingerprint == compiled.fingerprint
    archive = export_blueprint(package, tmp_path / "package.zip")
    with open_blueprint(archive) as extracted:
        assert extracted.fingerprint == package.fingerprint
        assert compile_blueprint(extracted).fingerprint == compiled.fingerprint


def test_published_inventory_and_explicit_unpublished_packages():
    roots = {record["repository"]: package_root(record).parent for record in BASELINE}
    ids = {
        name: {item["id"] for item in read_catalog(root / "index.json")}
        for name, root in roots.items()
    }
    assert ids == {
        repository: set(expected)
        for repository, expected in BASELINE_DOCUMENT["published_inventory"].items()
    }
    for record in BASELINE_DOCUMENT["retired_packages"]:
        assert record["id"] not in ids[record["repository"]]
        assert not package_root(record).exists()
    for record in BASELINE_DOCUMENT.get("renamed_packages", []):
        root = roots[record["repository"]]
        assert not (root / record["old_folder"]).exists()
        assert (root / record["new_folder"] / "manifest.json").is_file()
        assert record["old_id"] not in ids[record["repository"]]
        assert record["new_id"] in ids[record["repository"]]
        assert (
            read_blueprint(root / record["new_folder"]).manifest["id"]
            == record["new_id"]
        )
    for record in BASELINE_DOCUMENT["unpublished_packages"]:
        assert record["id"] not in ids[record["repository"]]
        assert read_blueprint(package_root(record)).manifest["id"] == record["id"]
    expected = {
        (repository, item["path"], item["id"])
        for repository, root in roots.items()
        for item in read_catalog(root / "index.json")
    } | {
        (record["repository"], record["path"], record["id"])
        for record in BASELINE_DOCUMENT["unpublished_packages"]
    }
    actual = [
        (record["repository"], record["path"], record["id"]) for record in BASELINE
    ]
    assert len(actual) == len(set(actual))
    assert set(actual) == expected, (
        "every published package needs the full transport witness"
    )
    assert not ids["otterdesk-blueprints"] & {
        "growth_partnerships_coworker",
        "business_finance_coworker",
        "learning_quality_safety_coworker",
        "content_studio_coworker",
    }


def test_review_binds_current_authored_and_payload_sources():
    for repository, expected in BASELINE_DOCUMENT[
        "reviewed_working_tree_sources"
    ].items():
        subjects = [row for row in BASELINE if row["repository"] == repository]
        root = package_root(subjects[0]).parent
        actual = {}
        for row in subjects:
            folder = package_root(row)
            for path in folder.rglob("*"):
                if (
                    path.is_file()
                    and path.suffix in {".py", ".md", ".json", ".js", ".css", ".html"}
                    and not {
                        "__pycache__",
                        ".venv",
                        ".pytest_cache",
                        "build",
                        "dist",
                        "tests",
                    }.intersection(path.relative_to(folder).parts)
                ):
                    actual[str(path.relative_to(root))] = hashlib.sha256(
                        path.read_bytes()
                    ).hexdigest()
        assert actual == expected, f"{repository}: reviewed source coverage/hash drift"
