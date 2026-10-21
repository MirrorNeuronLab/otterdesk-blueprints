"""Select declared review artifacts; SDK owns atomic output delivery."""
import os
from mn_sdk.blueprint_support import source_manifest
from mn_sdk.blueprint_support.shared_outputs import copy_path_to_host
from mn_sdk_common.committed_artifacts import CommittedJsonStore


def deliver_reports(block, *, presentation=False, complete=False):
    output = os.environ.get("MN_JOB_OUTPUT_DIR")
    if not output or CommittedJsonStore(output).run_dir == block.store.run_dir:
        return
    target = CommittedJsonStore(output)
    if block.store.run_dir in target.run_dir.parents:
        raise ValueError("Report staging and run directories must be separate.")
    for item in source_manifest(__file__)["contracts"]["outputs"]["artifacts"]:
        if (item["artifact_id"] in {"web_report", "web_ui"}) != presentation:
            continue
        source = block.store.path(item["path"])
        if not source.exists():
            if complete and item.get("required"):
                raise FileNotFoundError("A required review artifact is missing.")
            continue  # Failed extraction still delivers every available diagnostic.
        entries = list(source.rglob("*")) if source.is_dir() else [source]
        for entry in entries:
            relative = entry.relative_to(block.store.run_dir)
            block.store.path(relative)
            target.path(relative)
        copy_path_to_host(source, target.path(item["path"]))
