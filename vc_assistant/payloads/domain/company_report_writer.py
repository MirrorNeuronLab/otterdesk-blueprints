"""Native company report composition and verified source publication."""

from mn_sdk.agent_events import activity_operation
from mn_sdk.blueprint_support import utc_now_iso
from mn_sdk.integrations.block_files import materialize_file
from mn_sdk.integrations.block_publication_files import publish_files, merge_publications, deliver_files
from mn_sdk_common.publication import ArtifactWrite

from .artifact_sources import index_output_artifacts
from .intake_state import publish_snapshot, read_snapshot
from .outputs import compose_company_outputs
from .runtime_tools import append_event


def prepare_company_reports(block, state, clock):
    analyses = sorted(state["cached"]["analyses"].values(), key=lambda value: value["company_slug"])
    writes, inventory = compose_company_outputs(analyses, state["records"],
        state["cached"]["research_ledgers"], state["queue"], generated_at=clock)
    watch = {"run_id": block.run_id, "updated_at": clock, "companies": {
        item["company_slug"]: {**{key: item[key] for key in ("company_name", "fingerprint", "status", "document_count")},
                              "last_run_id": block.run_id} for item in state["queue"]}}
    import json
    writes.append(ArtifactWrite("watch_state", "watch_state.json", (json.dumps(watch, sort_keys=True) + "\n").encode(), kind="json", authoritative=True))
    publication = publish_files(block, writes, name="companies")
    deliver_files(block, publication)
    inventory = index_output_artifacts(block, inventory)
    source_writes = [ArtifactWrite(item["path"], item["path"], block.store.path(item["path"]).read_bytes())
        for item in inventory if item["kind"] in {"output_source_markdown", "output_source_catalog"}]
    for item in state["source_files"]:
        source = materialize_file(block, item["artifact"], path=block.root + "/input-sources/" + item["path"])
        source_writes.append(ArtifactWrite("input:" + item["path"], item["path"], source.read_bytes()))
    if source_writes:
        publication = merge_publications(block, publication, publish_files(block, source_writes, name="company-sources"))
    state.update(published_files=publication, output_files=inventory, watch_state=watch)
    append_event(block.store.run_dir, "watch_cycle_completed", {"cycle": 1, "companies": len(state["records"])})
    return state


@activity_operation('Writing company reports', completed='Writing company reports: completed')
def company_report_writer(block, inputs):
    state = read_snapshot(block, inputs, "score_consistency_auditor")
    clock_path = block.root + "/report-clock.json"
    clock = block.freeze_checkpoint(clock_path, lambda: utc_now_iso())
    path = block.root + "/prepared-company-publication.json"
    prepared = block.freeze_checkpoint(path,
        lambda: prepare_company_reports(block, state, block.read_checkpoint(clock, expected_path=clock_path)))
    state = block.read_checkpoint(prepared, expected_path=path)
    state["report_clock"] = clock.to_dict()
    return publish_snapshot(block, state, "company_report_writer",
        {"output_file_count": len(state["output_files"]), "published_files": state["published_files"]}, {})
