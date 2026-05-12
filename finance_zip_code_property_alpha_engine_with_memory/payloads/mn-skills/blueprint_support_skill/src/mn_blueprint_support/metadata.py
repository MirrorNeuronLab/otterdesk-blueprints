from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .constants import BLUEPRINT_CATEGORIES
from .utils import human_label, read_json_file


@dataclass(frozen=True)
class BlueprintMetadata:
    blueprint_id: str
    name: str
    description: str = ""
    category: str = ""
    graph_id: str = ""
    job_name: str = ""
    manifest_path: str | None = None
    runtime_features: tuple[str, ...] = ()

    @classmethod
    def from_manifest(cls, manifest_path: str | Path) -> "BlueprintMetadata":
        path = Path(manifest_path)
        manifest = read_json_file(path)
        metadata = manifest.get("metadata") or {}
        blueprint_id = str(metadata.get("blueprint_id") or manifest.get("name") or path.parent.name)
        return cls(
            blueprint_id=blueprint_id,
            name=str(metadata.get("name") or manifest.get("name") or human_label(blueprint_id)),
            description=str(metadata.get("description") or manifest.get("description") or ""),
            category=str(metadata.get("category") or ""),
            graph_id=str(manifest.get("graph_id") or ""),
            job_name=str(manifest.get("job_name") or ""),
            manifest_path=str(path),
            runtime_features=tuple(metadata.get("runtime_features") or ()),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "blueprint_id": self.blueprint_id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "graph_id": self.graph_id,
            "job_name": self.job_name,
            "manifest_path": self.manifest_path,
            "runtime_features": list(self.runtime_features),
        }


def infer_category(blueprint_id: str) -> str:
    for category in BLUEPRINT_CATEGORIES:
        if blueprint_id.startswith(f"{category}_"):
            return category
    return "general"
