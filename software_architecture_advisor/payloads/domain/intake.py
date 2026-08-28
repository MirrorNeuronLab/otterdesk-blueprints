"""Read-only source locator validation for the air-gapped analysis boundary."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .model_analysis import build_source_packet, run_model_stage, string_list, text, validate_references
from .state import inputs_for, write_state


def resolve_source(ctx: dict, *, llm_client: Any | None = None, **_options: object) -> dict:
    inputs = inputs_for(ctx)
    folder_value = inputs["input_folder"]
    github_url = inputs["github_repo_url"]
    if not folder_value and not github_url:
        raise ValueError("Provide input_folder or a github_repo_url that the connected intake service has pre-staged.")
    if github_url:
        _validate_github_url(github_url)
        if not folder_value:
            raise ValueError("github_repo_url must be materialized into input_folder before the air-gapped analysis begins.")
        if folder_value == "software_architecture_advisor/examples/sample_inputs":
            raise ValueError("The bundled demo folder cannot stand in for a requested GitHub snapshot; wait for intake staging.")
        source_kind = "github_pre_staged_snapshot"
    else:
        source_kind = "local_folder"
    folder = Path(folder_value).expanduser().resolve()
    if not folder.is_dir():
        raise ValueError(f"input_folder is not an accessible directory: {folder}")
    state = {
        "inputs": inputs,
        "source": {
            "kind": source_kind,
            "root": str(folder),
            "github_repo_url": github_url or None,
            "branch": inputs["branch"] if github_url else None,
            "network_egress": "forbidden",
            "source_execution": "forbidden",
        },
    }
    packet = build_source_packet(ctx, state, stage="source_intake")
    packet_paths = {str(item.get("path")) for item in packet.get("files") or [] if item.get("path")}
    fallback = {
        "summary": "Investigate documented entrypoints, module ownership, dependency direction, state, trust boundaries, deployment descriptors, and test seams before prioritizing changes.",
        "investigation_priorities": [
            {
                "question": "What are the repository's real entrypoints and stable ownership boundaries?",
                "rationale": "Documentation and configuration can identify intended composition before static dependency evidence is interpreted.",
                "evidence_targets": ["entrypoint declarations", "package descriptors", "architecture documentation"],
                "path_refs": sorted(packet_paths)[:5],
            }
        ],
        "entrypoint_hypotheses": [],
        "unknowns": ["Runtime topology, production traffic, operational ownership, and executed test results are not available at intake."],
    }

    def validate(value: dict[str, Any]) -> dict[str, Any] | None:
        if not isinstance(value, dict):
            return None
        priorities = value.get("investigation_priorities")
        if not isinstance(priorities, list) or not priorities:
            return None
        clean_priorities = []
        for item in priorities[:12]:
            if not isinstance(item, dict):
                return None
            refs = validate_references(item.get("path_refs"), packet_paths)
            targets = string_list(item.get("evidence_targets"), maximum_items=10)
            question = text(item.get("question"), maximum=900)
            rationale = text(item.get("rationale"), maximum=1400)
            if refs is None or targets is None or not question or not rationale:
                return None
            clean_priorities.append({"question": question, "rationale": rationale, "evidence_targets": targets, "path_refs": refs})
        hypotheses = []
        for item in value.get("entrypoint_hypotheses") or []:
            # Entrypoint hypotheses are optional. Reject malformed or ungrounded
            # candidates without discarding the otherwise valid investigation
            # plan; only normalized, path-grounded objects enter durable state.
            if not isinstance(item, dict) or str(item.get("path") or "") not in packet_paths:
                continue
            hypotheses.append({"path": str(item["path"]), "reason": text(item.get("reason"), maximum=1200)})
        unknowns = string_list(value.get("unknowns"), maximum_items=20)
        summary = text(value.get("summary"), maximum=3000)
        if unknowns is None or not summary:
            return None
        return {"summary": summary, "investigation_priorities": clean_priorities, "entrypoint_hypotheses": hypotheses[:12], "unknowns": unknowns}

    state["investigation_plan"] = run_model_stage(
        ctx,
        state,
        stage="source_intake",
        task="Create a repository-specific investigation plan from bounded documentation and metadata.",
        context=packet,
        fallback=fallback,
        validator=validate,
        llm_client=llm_client,
    )
    write_state(ctx, state)
    return {
        "source": {key: value for key, value in state["source"].items() if key != "root"},
        "investigation_priority_count": len(state["investigation_plan"]["investigation_priorities"]),
    }


def _validate_github_url(value: str) -> None:
    parsed = urlparse(value)
    if parsed.scheme != "https" or parsed.hostname not in {"github.com", "www.github.com"}:
        raise ValueError("github_repo_url must be an HTTPS URL on github.com; SSH, tokens, and arbitrary hosts are not allowed.")
    if parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise ValueError("github_repo_url cannot contain credentials, query parameters, or fragments.")
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) != 2:
        raise ValueError("github_repo_url must identify exactly one owner/repository path.")
