import json
import time


def test_retry_reuses_verified_source_capture_without_ingesting_again(tmp_path, monkeypatch, architecture_paths):
    from domain import intake
    from native_test_support import block_context
    source = tmp_path / "source"
    source.mkdir()
    run = tmp_path / "run"
    run.mkdir()
    snapshot = {"id": "frozen", "coverage": {"source_files": 3}, "modules": {"a": {}}}
    (run / "snapshot.json").write_text(json.dumps(snapshot))
    folder=run/'evidence/snapshots/frozen';folder.mkdir(parents=True)
    (folder/'sources.json').write_text('{}')
    before = (run / "snapshot.json").read_bytes()
    monkeypatch.setattr(intake, "policy", lambda _: {"offline": True})
    monkeypatch.setattr(intake, "load_snapshot", lambda _: {"manifest": snapshot})
    def forbidden(*args):
        raise AssertionError("Committed source capture must not ingest source again")
    monkeypatch.setattr(intake, "ingest_source", forbidden)
    context = {"payload": {"input_folder": str(source)}, "run_dir": str(run), "config": {}}
    assert intake.capture_input(block_context(context), context['payload'])["source_files"] == 3
    assert intake.capture_input(block_context(context), context['payload'])["source_files"] == 3
    assert (run / "snapshot.json").read_bytes() == before




def test_retry_budget_layers_settings_without_rewriting_original(monkeypatch, architecture_paths):
    from domain.retry_budget import effective_config, effective_deadline
    original = {"catalog_review": {"walltime_seconds": 1200}, "opencode": {"timeout_seconds": 60, "model": "original"}}
    monkeypatch.setenv("MN_RUN_RETRY_JSON", json.dumps({"configuration_overrides": {"catalog_review.walltime_seconds": 3600, "opencode.timeout_seconds": 120}, "consumed_seconds": 1200}))
    effective = effective_config(original)
    assert effective["opencode"]["model"] == "original"
    assert effective["opencode"]["timeout_seconds"] == 120
    assert original["catalog_review"]["walltime_seconds"] == 1200
    began = time.time()
    assert 2399 <= effective_deadline(began - 86400, 3600) - began <= 2401
