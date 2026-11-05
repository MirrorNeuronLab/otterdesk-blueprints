"""Review block behavior and code independently of local build numbering."""

from __future__ import annotations

import copy
import hashlib
import json
from importlib import metadata


def reviewed_block_manifest(manifest):
    """Keep code identities exact; validate build versions against this environment.

    A source commit can advance setuptools-scm versions without changing code.
    Runtime locks must still bind those actual versions and their full revision.
    The historical behavior witness instead pins all non-version lock data,
    including component content hashes, and uses its digest in worker bindings.
    """
    lock = manifest.get("metadata", {}).get("mn_blocks_lock")
    if not lock:
        return manifest
    from mn_sdk.blueprints.block_lock import block_revision

    for component in [lock, *lock["components"]]:
        installed = metadata.version(component["distribution"])
        if component["version"] != installed:
            raise ValueError(
                f"block lock version differs from installed {component['distribution']}"
            )
    expected_revision = block_revision(
        lock["source_revision"],
        lock["components"],
        lock["steps"],
        services=lock.get("services"),
        operations=lock.get("operations"),
        events=lock.get("events"),
    )
    if lock["revision"] != expected_revision:
        raise ValueError("block lock revision does not bind its exact implementations")
    stable = copy.deepcopy(lock)
    del stable["revision"]
    for component in [stable, *stable["components"]]:
        component["version"] = "<installed-build>"
    stable_revision = hashlib.sha256(
        json.dumps(
            stable,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
    ).hexdigest()
    result = copy.deepcopy(manifest)
    result["metadata"]["mn_blocks_lock"] = {**stable, "revision": lock["revision"]}

    def replace(value):
        if isinstance(value, dict):
            return {key: replace(item) for key, item in value.items()}
        if isinstance(value, list):
            return [replace(item) for item in value]
        if isinstance(value, str):
            # Lowered worker environments contain JSON-encoded bindings too.
            return value.replace(lock["revision"], stable_revision)
        return value

    return replace(result)


def scrub(value):
    if isinstance(value, dict):
        return {
            key: scrub(item)
            for key, item in value.items()
            if key != "MN_BLUEPRINT_CONFIG_JSON"
        }
    if isinstance(value, list):
        return [scrub(item) for item in value]
    return value


def digest(value):
    return hashlib.sha256(
        json.dumps(
            scrub(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    ).hexdigest()


def configuration_digest(value):
    # JSON numbers 1 and 1.0 have the same configuration semantics.
    def normalize(item):
        if isinstance(item, float) and item.is_integer():
            return int(item)
        if isinstance(item, dict):
            return {key: normalize(value) for key, value in item.items()}
        if isinstance(item, list):
            return [normalize(value) for value in item]
        return item

    return digest(normalize(value))


def configuration_leaves(value, path=""):
    if isinstance(value, dict) and value:
        return {
            pointer: leaf
            for key, item in value.items()
            for pointer, leaf in configuration_leaves(
                item, path + "/" + key.replace("~", "~0").replace("/", "~1")
            ).items()
        }
    return {path: value}
