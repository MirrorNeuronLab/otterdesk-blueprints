#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def main() -> int:
    config = json.loads(os.getenv("MN_BLUEPRINT_CONFIG_JSON", "{}") or "{}")
    folder = (
        (config.get("tax_documents") or {}).get("folder_path")
        or ((config.get("inputs") or {}).get("payload") or {}).get("document_folder")
        or ""
    )
    if not folder:
        print("No tax document folder configured; demo sample documents will be used until the user selects a local folder.")
        return 0
    path = resolve_tax_folder(config, str(folder))
    if not path.exists() or not path.is_dir():
        print(
            json.dumps(
                {
                    "ok": False,
                    "issues": [
                        {
                            "code": "tax.folder_not_found",
                            "message": f"Tax document folder was not found: {path}",
                            "help": "Choose a local folder that contains PDF, TXT, or JSON tax forms.",
                            "location": {
                                "source": "config",
                                "path": "tax_documents.folder_path",
                                "pointer": "/config/tax_documents/folder_path",
                            },
                        }
                    ],
                }
            )
        )
        return 1
    files = [item for item in path.iterdir() if item.is_file() and item.suffix.lower() in {".pdf", ".txt", ".json"}]
    if not files:
        print(
            json.dumps(
                {
                    "ok": False,
                    "issues": [
                        {
                            "code": "tax.folder_empty",
                            "message": "Tax document folder does not contain PDF, TXT, or JSON forms.",
                            "help": "Add tax source forms such as W-2, 1099-INT, 1099-R, 1099-DIV, 1098, or 1095-A.",
                            "location": {
                                "source": "config",
                                "path": "tax_documents.folder_path",
                                "pointer": "/config/tax_documents/folder_path",
                            },
                        }
                    ],
                }
            )
        )
        return 1
    print(f"Validated tax document folder with {len(files)} candidate file(s): {path}")
    return 0


def resolve_tax_folder(config: dict, folder: str) -> Path:
    path = Path(folder).expanduser()
    if path.exists():
        return path

    for spec in ((config.get("local_inputs") or {}).get("folders") or []):
        if not isinstance(spec, dict):
            continue
        runtime_path = str(spec.get("runtime_path") or spec.get("path_in_runtime") or "").strip()
        payload_path = str(spec.get("payload_path") or spec.get("target_path") or "").strip()
        if not runtime_path or not payload_path or runtime_path != folder:
            continue
        candidate = Path("payloads") / payload_path
        if candidate.exists():
            return candidate
    return path


if __name__ == "__main__":
    sys.exit(main())
