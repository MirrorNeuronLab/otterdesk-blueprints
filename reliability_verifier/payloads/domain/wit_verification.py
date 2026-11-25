"""Bind the frozen verification plan to the Rust reconciliation component."""
import json
import os
from pathlib import Path
import stat

from mn_sdk.blueprint.wasm import invoke_component


def reconcile(block, plan, records):
    fields = {key: value for key, value in plan.items() if key != "plan_id"}
    signed = {
        "canonical": json.dumps(fields, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")),
        "plan_id": plan["plan_id"],
    }
    return invoke_component("reconcile", {"signed_plan": signed, "records": records}, environment=block.environment)


def assess(block, selected, *, test_sources=None, paths=()):
    result = invoke_component("assess", {"selected": selected}, environment=block.environment)
    if test_sources is not None:
        from mn_comparison_evidence_skill.oracles import oracle_inventory
        result["inventory"] = oracle_inventory(test_sources, paths)
    return result


def capture_subject(block, root, suffixes):
    """Copy admitted input bytes into the guest and freeze its source snapshot."""
    from mn_folder_files_skill import ScanLimits, scan_folder
    from mn_verification_checks_skill.comparison import read_pair

    def capture(folder):
        scan = scan_folder(Path(folder).absolute(), suffixes=suffixes, check=block.check,
            limits=ScanLimits(max_depth=40, max_entries=30000, max_files=2000,
                              max_file_bytes=500000, max_total_bytes=10000000))
        files = {}
        omitted = [item.relative_path for item in scan.excluded]
        size = 0
        for item in scan.files:
            block.check()
            if any(p.startswith(".") and p != ".github" for p in Path(item.relative_path).parts):
                omitted.append(item.relative_path)
                continue
            with os.fdopen(os.open(item.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), "rb") as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    raise ValueError("Source changed during capture.")
                data = stream.read(500001)
            size += len(data)
            if len(data) > 500000 or size > 10000000:
                raise ValueError("Source grew beyond the capture limit.")
            files[item.relative_path] = data
        snapshot = invoke_component("capture", {"extensions": list(suffixes)}, environment=block.environment,
                                    input_files=files)
        return snapshot["files"], [*omitted, *snapshot["omitted"]]

    pair = read_pair(root, capture)
    if pair is None:
        files, omitted = capture(root)
        return files, omitted, None, None
    comparison, sides = pair
    return sides["head"], [], comparison, sides["base"]
