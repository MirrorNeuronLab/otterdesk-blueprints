"""Invoke the blueprint-owned static graph skill against the staged source."""

from __future__ import annotations

from typing import Any

from .model_analysis import (
    build_source_packet,
    known_fact_ids,
    known_paths,
    run_model_stage,
    string_list,
    text,
    validate_references,
)
from .state import read_state, write_state


def map_architecture(
    ctx: dict[str, Any], *, llm_client: Any | None = None, **_options: Any
) -> dict[str, Any]:
    # Installed from payloads/skills by the manifest before an air-gapped run.
    from mn_software_architecture_graph_skill import (
        build_architecture_graph,
        build_deep_evidence,
        build_inventory,
        compact_inventory,
    )

    state = read_state(ctx)
    source = state.get("source") or {}
    if not source.get("root"):
        raise ValueError("source intake state is missing; map_architecture must follow resolve_source")
    settings = (ctx.get("config") or {}).get("analysis") or {}
    inventory = build_inventory(source["root"], settings)
    graph = build_architecture_graph(inventory)
    deep_evidence = build_deep_evidence(source["root"], inventory, graph, settings)
    state["inventory"] = compact_inventory(inventory)
    state["graph"] = graph
    state["repository_profile"] = deep_evidence["repository_profile"]
    state["symbol_index"] = deep_evidence["symbol_index"]
    state["metrics"] = deep_evidence["metrics"]
    state["state_model"] = deep_evidence["state_model"]
    state["trust_model"] = deep_evidence["trust_model"]
    state["test_architecture"] = deep_evidence["test_architecture"]
    state["deployment_model"] = deep_evidence["deployment_model"]
    state["history_evidence"] = deep_evidence["history"]
    state["hotspots"] = deep_evidence["hotspots"]
    state["architecture_facts"] = deep_evidence["facts"]
    state["deterministic_reconstruction"] = deep_evidence["deterministic_reconstruction"]
    state["evidence_availability"] = deep_evidence["evidence_availability"]
    state["deep_analysis_limitations"] = deep_evidence["limitations"]
    packet = build_source_packet(ctx, state, stage="component_mapping")
    fact_ids = known_fact_ids(state)
    paths = known_paths(state)
    packages = state["repository_profile"].get("packages") or []
    fallback_components = []
    for index, package in enumerate(packages[:20], start=1):
        package_name = str(package.get("name") or f"component-{index}")
        package_paths = sorted(path for path in paths if path == package_name or path.startswith(f"{package_name}/"))[:20]
        cited = _facts_for_paths(state, package_paths)[:12]
        fallback_components.append({
            "component_id": f"component-{index}",
            "name": package_name,
            "responsibility": "Responsibility requires confirmation from code, documentation, tests, and maintainers.",
            "paths": package_paths,
            "fact_ids": cited,
        })
    if not fallback_components:
        fallback_components = [{
            "component_id": "repository-root",
            "name": state["inventory"].get("source_root_name") or "repository",
            "responsibility": "No cohesive package boundary was deterministically established.",
            "paths": sorted(paths)[:20],
            "fact_ids": sorted(fact_ids)[:5],
        }]
    component_fallback = {
        "summary": "The component map combines static package, entrypoint, import, symbol, and repository metadata evidence; runtime composition remains unverified.",
        "components": fallback_components,
        "entrypoints": [
            {"path": item["path"], "role": "Statically detected entrypoint candidate", "fact_ids": _facts_for_paths(state, [item["path"]])[:8]}
            for item in (state["repository_profile"].get("entrypoints") or [])[:20]
            if item.get("path") in paths
        ],
        "dependency_directions": [],
        "unknowns": list(state["deterministic_reconstruction"].get("unknowns") or []),
    }
    component_map = run_model_stage(
        ctx,
        state,
        stage="component_mapping",
        task="Reconstruct components, responsibilities, entrypoints, and dependency direction.",
        context=packet,
        fallback=component_fallback,
        validator=lambda value: _validate_component_map(value, fact_ids=fact_ids, paths=paths),
        llm_client=llm_client,
    )
    state["architecture_reconstruction"] = component_map

    cross_packet = build_source_packet(ctx, state, stage="cross_cutting_mapping")
    cross_packet["component_map"] = component_map
    cross_fallback = {
        "summary": "Cross-cutting behavior is reconstructed conservatively from state, trust, deployment, test, and dependency evidence; runtime interactions remain hypotheses.",
        "flows": [],
        "state_ownership": [],
        "trust_boundaries": [],
        "deployment_interactions": [],
        "test_observations": [],
        "unknowns": [
            "Runtime dispatch, traffic shape, failure recovery, production authority, and effective test coverage were not observed.",
        ],
    }
    state["cross_cutting_analysis"] = run_model_stage(
        ctx,
        state,
        stage="cross_cutting_mapping",
        task="Analyze flows, state ownership, trust boundaries, deployment, tests, and likely runtime interactions.",
        context=cross_packet,
        fallback=cross_fallback,
        validator=lambda value: _validate_cross_cutting(value, fact_ids=fact_ids, paths=paths),
        llm_client=llm_client,
    )
    write_state(ctx, state)
    return {
        "source_file_count": inventory["source_file_count"],
        "dependency_edge_count": len(graph["edges"]),
        "symbol_count": deep_evidence["symbol_index"]["symbol_count"],
        "architecture_fact_count": deep_evidence["facts"]["fact_count"],
        "structural_hotspot_count": len(deep_evidence["hotspots"]),
        "inventory_truncated": inventory["truncated"],
    }


def _facts_for_paths(state: dict[str, Any], wanted: list[str]) -> list[str]:
    selected = set(wanted)
    return [
        str(item["fact_id"])
        for item in ((state.get("architecture_facts") or {}).get("facts") or [])
        if selected.intersection(item.get("paths") or [])
    ]


def _validate_component_map(
    value: dict[str, Any], *, fact_ids: set[str], paths: set[str]
) -> dict[str, Any] | None:
    if not isinstance(value, dict) or not isinstance(value.get("components"), list) or not value["components"]:
        return None
    components = []
    for index, item in enumerate(value["components"][:30], start=1):
        if not isinstance(item, dict):
            return None
        item_paths = validate_references(item.get("paths"), paths, allow_empty=False)
        item_facts = validate_references(item.get("fact_ids"), fact_ids)
        name = text(item.get("name"), maximum=300)
        responsibility = text(item.get("responsibility"), maximum=1600)
        if item_paths is None or item_facts is None or not name or not responsibility:
            return None
        components.append({
            "component_id": text(item.get("component_id"), maximum=200) or f"component-{index}",
            "name": name,
            "responsibility": responsibility,
            "paths": item_paths,
            "fact_ids": item_facts,
        })
    entrypoints = _validate_reference_objects(value.get("entrypoints"), fact_ids=fact_ids, paths=paths, label_key="role")
    if entrypoints is None:
        return None
    directions = []
    for item in value.get("dependency_directions") or []:
        if not isinstance(item, dict):
            return None
        cited = validate_references(item.get("fact_ids"), fact_ids)
        cited_paths = validate_references(item.get("paths"), paths, allow_empty=False)
        if cited is None or cited_paths is None:
            return None
        directions.append({
            "from_component": text(item.get("from_component"), maximum=300),
            "to_component": text(item.get("to_component"), maximum=300),
            "relationship": text(item.get("relationship"), maximum=1000),
            "paths": cited_paths,
            "fact_ids": cited,
        })
    unknowns = string_list(value.get("unknowns"), maximum_items=24)
    summary = text(value.get("summary"), maximum=4000)
    if unknowns is None or not summary:
        return None
    return {"summary": summary, "components": components, "entrypoints": entrypoints, "dependency_directions": directions[:40], "unknowns": unknowns}


def _validate_reference_objects(
    values: Any, *, fact_ids: set[str], paths: set[str], label_key: str
) -> list[dict[str, Any]] | None:
    if not isinstance(values, list):
        return None
    result = []
    for item in values[:40]:
        if not isinstance(item, dict) or str(item.get("path") or "") not in paths:
            return None
        cited = validate_references(item.get("fact_ids"), fact_ids)
        if cited is None:
            return None
        result.append({"path": str(item["path"]), label_key: text(item.get(label_key), maximum=1400), "fact_ids": cited})
    return result


def _validate_cross_cutting(
    value: dict[str, Any], *, fact_ids: set[str], paths: set[str]
) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    result: dict[str, Any] = {"summary": text(value.get("summary"), maximum=5000)}
    if not result["summary"]:
        return None
    for field in ("flows", "state_ownership", "trust_boundaries", "deployment_interactions", "test_observations"):
        raw_items = value.get(field)
        if not isinstance(raw_items, list):
            return None
        clean = []
        for item in raw_items[:30]:
            if not isinstance(item, dict):
                return None
            cited = validate_references(item.get("fact_ids"), fact_ids, allow_empty=False)
            cited_paths = validate_references(item.get("paths"), paths)
            if cited is None or cited_paths is None:
                return None
            clean.append({
                "name": text(item.get("name") or item.get("subject"), maximum=400),
                "analysis": text(item.get("analysis") or item.get("interpretation"), maximum=1800),
                "confidence": text(item.get("confidence"), maximum=20).lower() or "low",
                "paths": cited_paths,
                "fact_ids": cited,
            })
        result[field] = clean
    unknowns = string_list(value.get("unknowns"), maximum_items=30)
    if unknowns is None:
        return None
    result["unknowns"] = unknowns
    return result
