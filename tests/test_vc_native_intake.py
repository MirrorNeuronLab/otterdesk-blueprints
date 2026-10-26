"""Compiled native VC intake, independent from the legacy workflow fixture."""
import importlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from mn_sdk.blueprints import blueprint_definition, compile_blueprint, read_blueprint, resolve_config
from mn_sdk.blueprints.worker_descriptors import resolved_worker_descriptor
from mn_sdk.integrations.block_worker import run
from mn_sdk_common.committed_artifacts import CommittedJsonStore
from mn_sdk.step_runtime import StepContext

ROOT = Path(__file__).resolve().parents[1] / "vc_assistant"
pytestmark = pytest.mark.usefixtures("workflow_budget_owner")


@pytest.fixture
def intake(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "payloads"))
    documents = tmp_path / "documents"
    company = documents / "acme"
    company.mkdir(parents=True)
    source = company / "pitch.txt"
    source.write_text("Company: Acme\nProduct: working prototype. Founder claims ARR $120000. PRIVATE_BODY.\n")
    package = read_blueprint(ROOT)
    configuration = resolve_config(package, {
        "inputs": {"payload": {"document_folder": str(documents), "input_folder": str(documents)}},
        "source_context": {"enabled": False}, "text_memory": {"enabled": False},
        "knowledge_rag": {"enabled": False, "required": False},
        "actor_review": {"llm_actor_ids": [], "use_context_engine": False},
        "llm": {"mode": "fake", "require_live": False},
        "backpressure": {"llm": {"min_interval_seconds": 0}},
    })
    compiled = compile_blueprint(package, configuration).manifest
    descriptor = tmp_path / "descriptor.json"
    descriptor.write_text(json.dumps(resolved_worker_descriptor(package, compiled, configuration)))
    values = {"MN_BLUEPRINT_MANIFEST_PATH": str(descriptor), "MN_RUN_DIR": str(tmp_path / "run"),
        "MN_JOB_OUTPUT_DIR": str(tmp_path / "output"), "MN_SDK_COMPONENTS_JSON": '["blueprint-blocks"]'}
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    source_definition = blueprint_definition(package, configuration)
    descriptors = {json.dumps(configuration.data, sort_keys=True): descriptor}

    def descriptor_for(config=None):
        selected = config or configuration.data
        key = json.dumps(selected, sort_keys=True)
        if key not in descriptors:
            resolved = resolve_config(package, selected)
            manifest = compile_blueprint(package, resolved).manifest
            path = tmp_path / f"descriptor-{len(descriptors)}.json"
            path.write_text(json.dumps(resolved_worker_descriptor(package, manifest, resolved)))
            descriptors[key] = path
        return descriptors[key]

    def invoke(role, inputs, *, model=None, job_id="job", config=None, identity=None, directory=None, env=None):
        spec = source_definition["agents"]["registry"][role]
        module = "domain.research_planner" if role == "research_planner" else "domain.intake_blocks"
        if role in {"company_identity_researcher", "funding_researcher", "market_comp_researcher",
                "traction_verifier", "rendered_page_researcher"}:
            module = "domain.public_researcher"
        elif role == "research_reconciler":
            module = "domain.research_reconciler"
        elif spec.get("lifecycle", {}).get("method"):
            module = "domain.valuation_scorer"
        elif role == "score_consistency_auditor":
            module = "domain.score_consistency_auditor"
        elif role in {"company_report_writer", "batch_index_writer"}:
            module = "domain." + role
        assert spec["with"]["instance"]["hooks"]["operation"] == module + ":" + role
        selected = {**values, "MN_BLUEPRINT_MANIFEST_PATH": str(descriptor_for(config)), **(env or {})}
        if directory is not None:
            selected["MN_RUN_DIR"] = str(directory)
        context = StepContext(step_id="intake", job_id=job_id, run_id="run", agent_id=role,
            idempotency_key=identity or "run/" + role, environment=selected,
            config=config or configuration.data, message={"body": {"step_input": inputs}})
        result = run(context, resources={"llm": model} if model else {}, **spec["with"])
        return result.outputs["result"]

    return SimpleNamespace(invoke=invoke, source=source, store=CommittedJsonStore(tmp_path / "run"),
        config=configuration.data, root=tmp_path, descriptor_for=descriptor_for)


def grouped(intake, **options):
    watched = intake.invoke("startup_folder_watcher", {}, **options)
    return intake.invoke("company_packet_grouper", {"previous": watched}, **options)


def test_native_intake_extracts_captured_bytes_and_replays_without_conversion(intake, monkeypatch):
    groups = grouped(intake)
    intake.source.write_text("Replaced after capture. No startup evidence.")
    extracted = intake.invoke("document_evidence_extractor", {"previous": groups})
    state = intake.store.read(intake.store.read(extracted)["state"])["data"]
    assert "PRIVATE_BODY" in state["records"]["Acme"][0]["text_preview"]
    module = importlib.import_module("domain.intake_blocks")
    monkeypatch.setattr(module, "scan_documents", lambda *_a, **_k: pytest.fail("Replay converted a completed input again"))
    assert intake.invoke("document_evidence_extractor", {"previous": groups}) == extracted
    normalized = intake.invoke("claim_normalizer", {"result": extracted})
    snapshot = intake.store.read(intake.store.read(normalized)["state"])["data"]
    assert snapshot["queue"][0]["company_name"] == "Acme"
    assert snapshot["evidence"]["Acme"]["claim_records"]
    assert not intake.store.path("workflow_state/runtime_context.json").exists()


def test_changed_captured_chunk_fails_before_ocr_or_normalization(intake, monkeypatch):
    groups = grouped(intake)
    state = intake.store.read(intake.store.read(groups)["state"])["data"]
    chunk = intake.store.read(state["files"][0]["artifact"])["chunks"][0]
    intake.store.path(chunk["path"]).write_bytes(b"corrupted evidence")
    module = importlib.import_module("domain.intake_blocks")
    monkeypatch.setattr(module, "scan_documents", lambda *_a, **_k: pytest.fail("Corrupt evidence reached conversion"))
    with pytest.raises(RuntimeError, match="mismatch"):
        intake.invoke("document_evidence_extractor", {"previous": groups})
    assert not intake.store.path("vc/intake/document_evidence_extractor.json").exists()


@pytest.mark.parametrize("changed", ["job", "configuration"])
def test_intake_checkpoint_scope_is_enforced_before_using_sources(intake, changed):
    watched = intake.invoke("startup_folder_watcher", {})
    config = json.loads(json.dumps(intake.config))
    if changed == "configuration":
        config["execution"]["max_company_workers"] = 2
    with pytest.raises(Exception, match="scope|configuration"):
        intake.invoke("company_packet_grouper", {"previous": watched},
            job_id="other" if changed == "job" else "job", config=config, identity="foreign")


def private_input(intake, reference, *, config=None, name="replica", source_store=None):
    from mn_sdk.integrations.block_handoff import export_value
    from mn_sdk.artifact_handoff import reference_key
    environment = {"MN_ARTIFACT_OUTPUT_DIR": str(intake.root / ("exports-" + name)),
        "MN_ARTIFACT_COMMIT_ID": "commit-" + name, "MN_ARTIFACT_PRODUCER": json.dumps({"run_id": "run"})}
    bundle, _ = export_value(reference, source_store or intake.store, environment)
    inputs = intake.root / ("private-inputs-" + name)
    inputs.mkdir()
    index = {}
    for ordinal, entry in enumerate(bundle["files"]):
        reference = entry["artifact"]
        target = inputs / f"{ordinal}.bin"
        target.write_bytes((Path(environment["MN_ARTIFACT_OUTPUT_DIR"]) / reference["path"]).read_bytes())
        index[reference_key(reference)] = {"reference": reference, "file": target.name}
    (inputs / "index.json").write_text(json.dumps(index))
    intake.source.unlink(missing_ok=True)
    replica = intake.root / name
    replica.mkdir()
    private_descriptor = replica / "manifest.json"
    private_descriptor.write_bytes(intake.descriptor_for(config).read_bytes())
    return bundle, replica, {"MN_ARTIFACT_INPUT_INDEX": str(inputs / "index.json"),
             "MN_JOB_OUTPUT_DIR": str(replica / "outputs"),
             "MN_BLUEPRINT_MANIFEST_PATH": str(private_descriptor)}


def test_native_intake_restores_complete_evidence_in_an_independent_worker(intake):
    bundle, replica, environment = private_input(intake, grouped(intake))
    result = intake.invoke("document_evidence_extractor", {"previous": bundle},
        directory=replica, env=environment)
    store = CommittedJsonStore(replica)
    state = store.read(store.read(result)["state"])["data"]
    assert "PRIVATE_BODY" in state["records"]["Acme"][0]["text_preview"]
    assert list(replica.glob("vc/captured-inputs/acme/pitch.txt"))
    assert {item["path"] for item in state["source_files"]} == {
        "context_sources/inputs.json", "context_sources/inputs/acme/pitch.txt.md",
    }
    assert (replica / "outputs/context_sources/inputs/acme/pitch.txt.md").exists()


def test_optional_native_actor_review_remains_private_and_durable(intake):
    class Model:
        provider, model, calls, fallback_calls = "fake", "synthetic", 0, 0
        prompts = []
        def generate_json(self, **request):
            self.calls += 1
            self.prompts.append(request)
            return {**request["fallback"], "provider": self.provider, "model": self.model}
    model = Model()
    config = json.loads(json.dumps(intake.config))
    config["actor_review"]["llm_actor_ids"] = ["startup_folder_watcher"]
    result = intake.invoke("startup_folder_watcher", {}, model=model, config=config)
    assert intake.invoke("startup_folder_watcher", {}, model=model, config=config) == result
    state = intake.store.read(intake.store.read(result)["state"])["data"]
    assert "startup_folder_watcher" in state["actor_findings"]
    assert model.calls == 1 and "PRIVATE_BODY" not in json.dumps(model.prompts)


def test_native_claim_review_uses_scoped_authored_memory(intake, text_memory_transport):
    class Model:
        provider, model, calls, fallback_calls = "fake", "synthetic", 0, 0
        def generate_json(self, **request):
            self.calls += 1
            self.prompt = json.loads(request["user_prompt"])
            return {**request["fallback"], "provider": self.provider, "model": self.model}
    model = Model()
    config = json.loads(json.dumps(intake.config))
    config["text_memory"]["enabled"] = True
    config["actor_review"].update(llm_actor_ids=["claim_normalizer"], use_context_engine=True)
    groups = grouped(intake, config=config, model=model)
    extracted = intake.invoke("document_evidence_extractor", {"previous": groups}, config=config, model=model)
    normalized = intake.invoke("claim_normalizer", {"result": extracted}, config=config, model=model)
    assert model.calls == 1
    assert model.prompt["context"]["runtime_memory"]["evidence"]
    assert ("job", "run") in text_memory_transport.scopes
    assert list(intake.store.run_dir.glob("vc/memory/*.json"))
    assert intake.store.read(intake.store.read(normalized)["state"])["data"]["actor_findings"]["claim_normalizer"]
    state = intake.store.read(intake.store.read(normalized)["state"])["data"]
    witness = state["memory_witnesses"]["claim_normalizer"]
    from mn_sdk.integrations.block_handoff import export_value
    bundle, _ = export_value(normalized, intake.store, {
        "MN_ARTIFACT_OUTPUT_DIR": str(intake.root / "witness-export"),
        "MN_ARTIFACT_COMMIT_ID": "witness", "MN_ARTIFACT_PRODUCER": json.dumps({"run_id": "run"})})
    assert any(entry["committed"] == witness for entry in bundle["files"])
    assert state["review_contexts"]["claim_normalizer"]


def normalized(intake, **options):
    groups = grouped(intake, **options)
    extracted = intake.invoke("document_evidence_extractor", {"previous": groups}, **options)
    return intake.invoke("claim_normalizer", {"result": extracted}, **options)


def planning_config(intake, *, review=False):
    config = json.loads(json.dumps(intake.config))
    config["agentic_research"] = {"enabled": True, "agent_ids": ["research_planner"],
        "max_iterations_per_agent": 1, "max_tool_calls_per_agent": 1, "allowed_tools": ["finish"]}
    config["internet_research"]["enabled"] = False
    if review:
        config["actor_review"]["llm_actor_ids"] = ["research_planner"]
    return config


class PlanningModel:
    provider, model, calls, fallback_calls = "fake", "synthetic", 0, 0

    def generate_json(self, **request):
        self.calls += 1
        return {**request["fallback"], "tool_calls": [{"tool": "finish"}],
            "provider": self.provider, "model": self.model}


def test_known_review_reply_replays_its_frozen_context_after_interruption(intake, monkeypatch):
    config, model = json.loads(json.dumps(intake.config)), PlanningModel()
    config["actor_review"]["llm_actor_ids"] = ["startup_folder_watcher"]
    module = importlib.import_module("domain.intake_review")
    review = module.run_vc_actor_reviews
    def interrupted(**options):
        review(**options)
        raise KeyboardInterrupt("synthetic interruption after observed model reply")
    monkeypatch.setattr(module, "run_vc_actor_reviews", interrupted)
    with pytest.raises(KeyboardInterrupt):
        intake.invoke("startup_folder_watcher", {}, config=config, model=model)
    assert model.calls == 1
    monkeypatch.setattr(module, "run_vc_actor_reviews", review)
    monkeypatch.setattr(module, "retrieve_knowledge_rag_context", lambda **_kw: pytest.fail("Replay retrieved a different review context"))
    result = intake.invoke("startup_folder_watcher", {}, config=config, model=model)
    state = intake.store.read(intake.store.read(result)["state"])["data"]
    assert state["review_contexts"]["startup_folder_watcher"]
    assert model.calls == 1 and state["action_ledger"]["used"] == 1


def test_native_planner_uses_snapshot_instead_of_mutable_workflow_views(intake, monkeypatch):
    config, model = planning_config(intake), PlanningModel()
    evidence = normalized(intake, config=config)
    (intake.store.run_dir / "workflow_state/company_records.json").write_text('{"Forged": []}')
    result = intake.invoke("research_planner", {"previous": evidence}, config=config, model=model)
    state = intake.store.read(intake.store.read(result)["state"])["data"]
    assert set(state["cached"]["research_plans"]) == {"Acme"}
    assert state["action_ledger"]["used"] == 1 and model.calls == 1
    module = importlib.import_module("domain.research_planner")
    monkeypatch.setattr(module, "plan_snapshot", lambda *_a: pytest.fail("Planning replay repeated model/tool work"))
    assert intake.invoke("research_planner", {"previous": evidence}, config=config, model=model) == result
    assert not intake.store.path("workflow_state/runtime_context.json").exists()


def test_interrupted_planning_outcome_fences_another_model_dispatch(intake):
    from mn_blueprint_blocks import BlockError
    config = planning_config(intake)
    evidence = normalized(intake, config=config)
    model = PlanningModel()

    def interrupted(**request):
        model.calls += 1
        raise KeyboardInterrupt("synthetic lost planning outcome")

    model.generate_json = interrupted
    with pytest.raises(KeyboardInterrupt):
        intake.invoke("research_planner", {"previous": evidence}, config=config, model=model)
    with pytest.raises(BlockError) as failure:
        intake.invoke("research_planner", {"previous": evidence}, config=config, model=model)
    assert failure.value.code == "outcome_unknown" and model.calls == 1
    assert not intake.store.path("vc/intake/research_planner.json").exists()


def test_optional_review_interruption_keeps_its_charge_and_saved_plan(intake):
    config, model = planning_config(intake, review=True), PlanningModel()
    evidence = normalized(intake, config=config)
    generate = model.generate_json

    def interrupted_review(**request):
        if model.calls == 1:
            model.calls += 1
            raise KeyboardInterrupt("synthetic lost review outcome")
        return generate(**request)

    model.generate_json = interrupted_review
    with pytest.raises(KeyboardInterrupt):
        intake.invoke("research_planner", {"previous": evidence}, config=config, model=model)
    result = intake.invoke("research_planner", {"previous": evidence}, config=config, model=model)
    state = intake.store.read(intake.store.read(result)["state"])["data"]
    assert model.calls == 2 and state["action_ledger"]["used"] == 2
    assert state["actor_findings"]["research_planner"]["provider"] == "actor_review_unavailable"
    assert state["actor_review_warnings"]
    assert json.loads(intake.store.path("workflow_state/action_ledger.json").read_text())["used"] == 2


def test_native_planner_rejects_another_job_before_model_initialization(intake, monkeypatch):
    config = planning_config(intake)
    evidence = normalized(intake, config=config)
    module = importlib.import_module("domain.research_services")
    monkeypatch.setattr(module, "get_actor_llm_client", lambda *_a: pytest.fail("Foreign evidence reached model initialization"))
    with pytest.raises(Exception, match="scope|configuration"):
        intake.invoke("research_planner", {"previous": evidence}, config=config, job_id="other")


def test_native_planner_runs_in_private_worker_with_only_its_verified_input_graph(intake):
    config, model = planning_config(intake), PlanningModel()
    evidence = normalized(intake, config=config)
    bundle, replica, environment = private_input(intake, evidence)
    result = intake.invoke("research_planner", {"previous": bundle}, directory=replica,
        env=environment, config=config, model=model)
    store = CommittedJsonStore(replica)
    state = store.read(store.read(result)["state"])["data"]
    assert set(state["cached"]["research_plans"]) == {"Acme"}
    assert model.calls == 1 and state["action_ledger"]["used"] == 1
    assert not store.path("workflow_state/runtime_context.json").exists()


def public_config(intake, limit=160):
    config = json.loads(json.dumps(intake.config))
    config["agentic_research"] = {"enabled": False}
    config["internet_research"]["enabled"] = True
    config["research_budget"]["default_actions"] = limit
    return config


def planned(intake, config):
    evidence = normalized(intake, config=config)
    return intake.invoke("research_planner", {"previous": evidence}, config=config)


def install_public_tool(monkeypatch, calls, *, interrupted=False):
    module = importlib.import_module("domain.public_researcher")
    from domain.research_core import _source_record
    def research(company, role, query, plan, internet, run_dir, budget):
        action = budget.start(action_type="browser_search", stage=role,
            entity_id=company, tool="synthetic_browser", metadata={"query": query})
        if action is not None:
            calls.append((company, role))
            if interrupted:
                raise KeyboardInterrupt("synthetic lost browser outcome")
            budget.complete(action, "completed", {"source_count": 1})
        status = "ok" if action is not None else "budget_exhausted"
        return role, [_source_record(company=company, query=str(query),
            url="https://example.invalid/" + role, title="Synthetic public registry",
            snippet="Independent public registry evidence" if action else "Research action allowance exhausted",
            status=status, skill="web_browser_skill", verification_target=role)]
    monkeypatch.setattr(module, "_run_research_agent", research)


def stage_research_join(intake, outputs, config, *, name="reconcile-worker"):
    from mn_sdk.integrations.block_handoff import export_value
    from mn_sdk.artifact_handoff import reference_key
    private = intake.root / name
    private.mkdir()
    inputs = private / "inputs"
    inputs.mkdir()
    index, packets = {}, {}
    for role, (result, store) in outputs.items():
        environment = {"MN_ARTIFACT_OUTPUT_DIR": str(intake.root / (name + "-export-" + role)),
            "MN_ARTIFACT_COMMIT_ID": name + "-" + role, "MN_ARTIFACT_PRODUCER": json.dumps({"run_id": "run"})}
        bundle, _ = export_value(result, store, environment)
        packets[role] = {"result": bundle}
        for ordinal, entry in enumerate(bundle["files"]):
            reference = entry["artifact"]
            target = inputs / f"{role}-{ordinal}.bin"
            target.write_bytes((Path(environment["MN_ARTIFACT_OUTPUT_DIR"]) / reference["path"]).read_bytes())
            index[reference_key(reference)] = {"reference": reference, "file": target.name}
    (inputs / "index.json").write_text(json.dumps(index))
    descriptor = private / "manifest.json"
    descriptor.write_bytes(intake.descriptor_for(config).read_bytes())
    return private, packets, {"MN_ARTIFACT_INPUT_INDEX": str(inputs / "index.json"),
        "MN_BLUEPRINT_MANIFEST_PATH": str(descriptor), "MN_JOB_OUTPUT_DIR": str(private / "outputs")}


def test_parallel_private_research_workers_share_one_action_and_join_verified_evidence(intake, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from domain.common import RESEARCH_AGENT_IDS
    config, calls = public_config(intake, limit=1), []
    plan = planned(intake, config)
    install_public_tool(monkeypatch, calls)
    prepared = {role: private_input(intake, plan, config=config, name=role)
        for role in RESEARCH_AGENT_IDS}
    def collect(role):
        bundle, directory, environment = prepared[role]
        reference = intake.invoke(role, {"previous": bundle}, directory=directory,
            env=environment, config=config)
        return role, (reference, CommittedJsonStore(directory))
    with ThreadPoolExecutor(5) as pool:
        outputs = dict(pool.map(collect, RESEARCH_AGENT_IDS))
    assert len(calls) == 1
    directory, packets, environment = stage_research_join(intake, outputs, config)
    result = intake.invoke("research_reconciler", {"previous": packets}, directory=directory,
        env=environment, config=config)
    store = CommittedJsonStore(directory)
    state = store.read(store.read(result)["state"])["data"]
    assert state["action_ledger"]["used"] == 1
    assert sum(action["cost"] for action in state["action_ledger"]["actions"]) == 1
    assert set(state["cached"]["research_ledgers"]["Acme"]) >= set(RESEARCH_AGENT_IDS)
    assert len(state["cached"]["reconciliations"]) == 1
    assert set(state["research_branches"]) == set(RESEARCH_AGENT_IDS)
    assert not store.path("workflow_state/runtime_context.json").exists()
    assert intake.invoke("research_reconciler", {"previous": packets}, directory=directory,
        env=environment, config=config) == result
    assert len(calls) == 1


def test_unknown_public_research_outcome_fences_browser_redispatch(intake, monkeypatch):
    from mn_blueprint_blocks import BlockError
    config, calls = public_config(intake), []
    plan = planned(intake, config)
    install_public_tool(monkeypatch, calls, interrupted=True)
    with pytest.raises(KeyboardInterrupt):
        intake.invoke("funding_researcher", {"previous": plan}, config=config)
    with pytest.raises(BlockError) as failure:
        intake.invoke("funding_researcher", {"previous": plan}, config=config)
    assert failure.value.code == "outcome_unknown" and len(calls) == 1


@pytest.mark.parametrize("role", ["research_planner", "rendered_page_researcher"])
def test_research_preparation_failure_can_retry_before_dispatch(intake, monkeypatch, role):
    from mn_sdk_rag import RagError

    config, calls = public_config(intake), []
    install_public_tool(monkeypatch, calls)
    upstream = normalized(intake, config=config) if role == "research_planner" else planned(intake, config)
    if role != "research_planner":
        # Another specialist's admitted work does not make this scope uncertain.
        intake.invoke("funding_researcher", {"previous": upstream}, config=config)
    module = importlib.import_module("domain.research_planner" if role == "research_planner"
        else "domain.public_researcher")
    prepare = module.research_resources
    def unavailable(*args, **kwargs):
        raise RagError("Synthetic knowledge retrieval failed with HTTP 503")
    monkeypatch.setattr(module, "research_resources", unavailable)
    for _ in range(2):
        with pytest.raises(RagError, match="HTTP 503"):
            intake.invoke(role, {"previous": upstream}, config=config)
    assert len(calls) == (0 if role == "research_planner" else 1)
    monkeypatch.setattr(module, "research_resources", prepare)
    result = intake.invoke(role, {"previous": upstream}, config=config)
    assert intake.invoke(role, {"previous": upstream}, config=config) == result
    assert len(calls) == (0 if role == "research_planner" else 2)


def test_checkpoint_recovery_does_not_repeat_research_when_another_worker_spends(intake, monkeypatch):
    config, calls = public_config(intake), []
    plan = planned(intake, config)
    install_public_tool(monkeypatch, calls)
    module = importlib.import_module("domain.intake_state")
    write = module.write_workflow_state
    def interrupted(run_dir, path, value):
        if path.startswith("research_ledgers_by_agent/funding_researcher/"):
            raise OSError("synthetic lost inspection-view write")
        return write(run_dir, path, value)
    monkeypatch.setattr(module, "write_workflow_state", interrupted)
    with pytest.raises(OSError):
        intake.invoke("funding_researcher", {"previous": plan}, config=config)
    frozen = intake.store.read_path("vc/intake/funding_researcher.json")
    intake.invoke("traction_verifier", {"previous": plan}, config=config)
    monkeypatch.setattr(module, "write_workflow_state", write)
    result = intake.invoke("funding_researcher", {"previous": plan}, config=config)
    assert intake.store.read(intake.store.read(result)["state"]) == frozen
    assert frozen["data"]["action_ledger"]["used"] == 1 and len(calls) == 2


def test_reconciliation_rejects_missing_or_mislabeled_branches_before_work(intake, monkeypatch):
    config = public_config(intake)
    plan = planned(intake, config)
    calls = []
    install_public_tool(monkeypatch, calls)
    one = intake.invoke("funding_researcher", {"previous": plan}, config=config)
    module = importlib.import_module("domain.research_reconciler")
    monkeypatch.setattr(module, "append_financial_tool_research", lambda *_a, **_kw: pytest.fail("Invalid join reached financial work"))
    with pytest.raises(ValueError, match="explicit research join"):
        intake.invoke("research_reconciler", {"previous": {"funding_researcher": {"result": one}}}, config=config)


def reconciled(intake, config):
    from domain.common import RESEARCH_AGENT_IDS
    plan = planned(intake, config)
    packets = {role: {"result": intake.invoke(role, {"previous": plan}, config=config)}
        for role in RESEARCH_AGENT_IDS}
    return intake.invoke("research_reconciler", {"previous": packets}, config=config)


def scoring_config(intake):
    config = public_config(intake)
    config["internet_research"]["enabled"] = False
    return config


def test_parallel_private_scorers_preserve_formulas_and_share_review_allowance(intake, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from domain.common import SCORER_AGENT_BY_METHOD
    from domain.valuation import METHOD_SCORER_FUNCTIONS
    config, model = scoring_config(intake), PlanningModel()
    config["research_budget"]["default_actions"] = 2
    config["actor_review"]["llm_actor_ids"] = list(SCORER_AGENT_BY_METHOD.values())
    evidence = reconciled(intake, config)
    # Mutable views cannot create or replace a score in native workers.
    intake.store.path("workflow_state/company_records.json").write_text('{"Forged": []}')
    policy = importlib.import_module("domain.research_policy")
    monkeypatch.setattr(policy, "utc_now_iso", lambda: pytest.fail("Native scoring rebuilt its frozen fact table"))
    prepared = {role: private_input(intake, evidence, config=config, name=role)
        for role in SCORER_AGENT_BY_METHOD.values()}
    def score(role):
        bundle, directory, environment = prepared[role]
        result = intake.invoke(role, {"previous": bundle}, directory=directory,
            env=environment, config=config, model=model)
        store = CommittedJsonStore(directory)
        snapshot = store.read(store.read(result)["state"])["data"]
        branch = snapshot["score_branch"]
        assert set(branch["scores"]) == {"Acme"}
        assert branch["scores"]["Acme"] == METHOD_SCORER_FUNCTIONS[branch["method"]](branch["facts"]["Acme"])
        assert snapshot["review_contexts"][role]
        assert not store.path("workflow_state/runtime_context.json").exists()
        assert intake.invoke(role, {"previous": bundle}, directory=directory,
            env=environment, config=config, model=model) == result
        return role, (result, store)
    with ThreadPoolExecutor(7) as pool:
        outputs = dict(pool.map(score, SCORER_AGENT_BY_METHOD.values()))
    assert model.calls == 1  # Reconciliation consumed the first action; all reviews share the second.
    directory, packets, environment = stage_research_join(intake, outputs, config, name="score-join")
    audited = intake.invoke("score_consistency_auditor", {"previous": packets},
        directory=directory, env=environment, config=config)
    store = CommittedJsonStore(directory)
    state = store.read(store.read(audited)["state"])["data"]
    assert state["action_ledger"]["used"] == 2
    assert set(state["scoring_branches"]) == set(SCORER_AGENT_BY_METHOD.values())
    analysis = state["cached"]["analyses"]["Acme"]
    assert analysis["fact_table"] == state["fact_tables"]["Acme"]
    assert set(analysis["methods"]) == set(SCORER_AGENT_BY_METHOD)
    assert analysis["audit"]["status"] in {"checked", "checked_with_warnings"}
    assert set(state["actor_findings"]) == set(SCORER_AGENT_BY_METHOD.values())
    module = importlib.import_module("domain.score_consistency_auditor")
    monkeypatch.setattr(module, "build_company_analysis_from_method_scores", lambda *_a, **_kw: pytest.fail("Replay audited again"))
    assert intake.invoke("score_consistency_auditor", {"previous": packets},
        directory=directory, env=environment, config=config) == audited
    assert model.calls == 1


@pytest.mark.parametrize("fault", ["missing", "wrong_role", "foreign_job", "tamper"])
def test_native_audit_rejects_invalid_scoring_handoffs_before_domain_work(intake, monkeypatch, fault):
    from domain.common import SCORER_AGENT_BY_METHOD
    config = scoring_config(intake)
    evidence = reconciled(intake, config)
    roles = list(SCORER_AGENT_BY_METHOD.values())
    packets = {role: {"result": intake.invoke(role, {"previous": evidence}, config=config)} for role in roles}
    if fault == "missing":
        packets.pop(roles[-1])
    elif fault == "wrong_role":
        packets[roles[-1]] = packets[roles[0]]
    elif fault == "tamper":
        state_ref = intake.store.read(packets[roles[-1]]["result"])["state"]
        intake.store.path(state_ref["path"]).write_text('{}')
    module = importlib.import_module("domain.score_consistency_auditor")
    monkeypatch.setattr(module, "build_company_analysis_from_method_scores", lambda *_a, **_kw: pytest.fail("Invalid score join reached audit"))
    with pytest.raises(Exception, match="specialists|path|scope|mismatch"):
        intake.invoke("score_consistency_auditor", {"previous": packets}, config=config,
            job_id="other" if fault == "foreign_job" else "job")
    assert not intake.store.path("vc/intake/score_consistency_auditor.json").exists()


def test_scorer_review_recalls_its_actual_method_with_formula_and_qualifications(intake, text_memory_transport):
    from domain.common import SCORER_AGENT_BY_METHOD
    config = scoring_config(intake)
    config["text_memory"]["enabled"] = True
    config["actor_review"].update(llm_actor_ids=["berkus_scorer"], use_context_engine=True)
    evidence = reconciled(intake, config)
    class Model(PlanningModel):
        def generate_json(self, **request):
            self.prompt = json.loads(request["user_prompt"])
            return super().generate_json(**request)
    model = Model()
    scored = intake.invoke("berkus_scorer", {"previous": evidence}, config=config, model=model)
    state = intake.store.read(intake.store.read(scored)["state"])["data"]
    witness = intake.store.read(state["memory_witnesses"]["berkus_scorer"])
    method = next(method for method, role in SCORER_AGENT_BY_METHOD.items() if role == "berkus_scorer")
    assert any(item.get("method_id") == method for item in witness["inputs"])
    recalled = json.dumps(model.prompt["context"]["runtime_memory"])
    assert method in recalled
    assert state["score_branch"]["scores"]["Acme"]["formula_or_weighting"] in recalled
    assert "quality_management_team" in recalled  # The actual Berkus bucket values travel with the formula.
    assert "runtime_method_result" in recalled and "PRIVATE_BODY" not in recalled
    assert model.calls == 1


@pytest.mark.parametrize("fault", ["method", "coverage", "facts", "base"])
def test_native_audit_rejects_validly_committed_but_inconsistent_score_branches(intake, monkeypatch, fault):
    from domain.common import SCORER_AGENT_BY_METHOD
    config = scoring_config(intake)
    evidence = reconciled(intake, config)
    roles = list(SCORER_AGENT_BY_METHOD.values())
    module = importlib.import_module("domain.valuation_scorer")
    calculate = module.score_snapshot
    def invalid(*args):
        state = calculate(*args)
        branch = state["score_branch"]
        if branch["agent_id"] == roles[-1]:
            if fault == "method":
                branch["scores"]["Acme"]["method_id"] = "another_method"
            elif fault == "coverage":
                branch["scores"] = {}
            elif fault == "facts":
                branch["facts"]["Acme"]["company_name"] = "Different company facts"
            else:
                branch["base"] = state["research_branches"]["funding_researcher"]
        return state
    monkeypatch.setattr(module, "score_snapshot", invalid)
    packets = {role: {"result": intake.invoke(role, {"previous": evidence}, config=config)} for role in roles}
    audit = importlib.import_module("domain.score_consistency_auditor")
    monkeypatch.setattr(audit, "build_company_analysis_from_method_scores", lambda *_a, **_kw: pytest.fail("Inconsistent branches reached audit"))
    with pytest.raises(ValueError, match="method|coverage|facts|authority"):
        intake.invoke("score_consistency_auditor", {"previous": packets}, config=config)


def test_audit_retry_preserves_checked_time_and_known_review_without_recomputing(intake, monkeypatch):
    from domain.common import SCORER_AGENT_BY_METHOD
    config, model = scoring_config(intake), PlanningModel()
    config["actor_review"]["llm_actor_ids"] = ["score_consistency_auditor"]
    evidence = reconciled(intake, config)
    packets = {role: {"result": intake.invoke(role, {"previous": evidence}, config=config)}
        for role in SCORER_AGENT_BY_METHOD.values()}
    review_module = importlib.import_module("domain.intake_review")
    review = review_module.run_vc_actor_reviews
    def interrupted(**options):
        review(**options)
        raise KeyboardInterrupt("synthetic interruption after audit review reply")
    monkeypatch.setattr(review_module, "run_vc_actor_reviews", interrupted)
    with pytest.raises(KeyboardInterrupt):
        intake.invoke("score_consistency_auditor", {"previous": packets}, config=config, model=model)
    assert model.calls == 1
    prepared = next(intake.store.run_dir.glob("blocks/*/prepared-audit.json"))
    analysis = json.loads(prepared.read_text())["data"]["cached"]["analyses"]["Acme"]
    monkeypatch.setattr(review_module, "run_vc_actor_reviews", review)
    module = importlib.import_module("domain.score_consistency_auditor")
    monkeypatch.setattr(module, "build_company_analysis_from_method_scores", lambda *_a, **_kw: pytest.fail("Pending audit recomputed its time/evidence"))
    audited = intake.invoke("score_consistency_auditor", {"previous": packets}, config=config, model=model)
    state = intake.store.read(intake.store.read(audited)["state"])["data"]
    assert state["cached"]["analyses"]["Acme"] == analysis
    assert state["review_contexts"]["score_consistency_auditor"]
    assert state["action_ledger"]["used"] == 2 and model.calls == 1


def audited(intake, config):
    from domain.common import SCORER_AGENT_BY_METHOD
    evidence = reconciled(intake, config)
    packets = {role: {"result": intake.invoke(role, {"previous": evidence}, config=config)}
        for role in SCORER_AGENT_BY_METHOD.values()}
    return intake.invoke("score_consistency_auditor", {"previous": packets}, config=config)


def publication_config(intake):
    config = scoring_config(intake)
    config["actor_review"]["llm_actor_ids"] = ["company_report_writer", "batch_index_writer"]
    return config


def test_native_publication_crosses_private_workers_with_complete_sources_and_replay(intake, text_memory_transport):
    config, model = publication_config(intake), PlanningModel()
    config["source_context"]["enabled"] = True
    evidence = audited(intake, config)
    bundle, company_dir, company_env = private_input(intake, evidence, config=config, name="company-worker")
    companies = intake.invoke("company_report_writer", {"previous": bundle}, directory=company_dir,
        env=company_env, config=config, model=model)
    company_store = CommittedJsonStore(company_dir)
    assert intake.invoke("company_report_writer", {"previous": bundle}, directory=company_dir,
        env=company_env, config=config, model=model) == companies
    assert (company_dir / "outputs/acme/analysis.md").is_file()
    next_bundle, batch_dir, batch_env = private_input(intake, companies, config=config,
        name="batch-worker", source_store=company_store)
    result = intake.invoke("batch_index_writer", {"previous": next_bundle}, directory=batch_dir,
        env=batch_env, config=config, model=model)
    store = CommittedJsonStore(batch_dir)
    output = store.read_path("final_artifact.json")
    assert len(output["company_reports"]) == 1 and len(output["company_reports"][0]["methods"]) == 7
    assert output["action_ledger"]["used"] == 3 and model.calls == 2
    assert output["llm_usage"]["calls"] == 2
    assert output["actor_findings"]["company_report_writer"] and output["actor_findings"]["batch_index_writer"]
    assert intake.invoke("batch_index_writer", {"previous": next_bundle}, directory=batch_dir,
        env=batch_env, config=config, model=model) == result
    assert model.calls == 2
    assert (batch_dir / "outputs/final_artifact.json").read_bytes() == store.path("final_artifact.json").read_bytes()
    assert "PRIVATE_BODY" in (batch_dir / "outputs/context_sources/inputs/acme/pitch.txt.md").read_text()
    assert (batch_dir / "outputs/context_sources/outputs/final_artifact.json.md").is_file()
    assert (batch_dir / "outputs/watch_state.json").is_file()
    assert not (batch_dir / "outputs/result.json").exists()
    assert not store.path("workflow_state/runtime_context.json").exists()
    from mn_context_engine_sdk.intelligent_system import corpus_job_id
    scope = (corpus_job_id("job", "sources"), None)
    assert scope in text_memory_transport.scopes
    assert any("score-only" in body for body in text_memory_transport.scopes[scope].values())


@pytest.mark.parametrize("interruption", ["delivery", "source_index"])
def test_company_publication_retry_preserves_coverage_bytes(intake, monkeypatch, interruption):
    from mn_sdk.blueprint_support import shared_outputs
    writer = importlib.import_module("domain.company_report_writer")
    reporting = importlib.import_module("domain.reporting")
    clock = "2026-01-01T00:00:00+00:00"
    monkeypatch.setattr(writer, "utc_now_iso", lambda: clock)
    monkeypatch.setattr(reporting, "utc_now_iso", lambda: clock)
    config, model = publication_config(intake), PlanningModel()
    evidence = audited(intake, config)
    copy, index = shared_outputs.copy_path_to_host, writer.index_output_artifacts

    def interrupted_copy(source, target):
        if Path(target).name == "company_index.json":
            raise OSError("synthetic company publication interruption")
        return copy(source, target)

    def interrupted_index(*args):
        raise OSError("synthetic company publication interruption")

    if interruption == "delivery":
        monkeypatch.setattr(shared_outputs, "copy_path_to_host", interrupted_copy)
    else:
        monkeypatch.setattr(writer, "index_output_artifacts", interrupted_index)
    with pytest.raises(OSError, match="publication interruption"):
        intake.invoke("company_report_writer", {"previous": evidence}, config=config, model=model)
    receipt_path = next(intake.store.run_dir.glob("blocks/*/publications/*/receipts/0.json"))
    receipt_bytes = receipt_path.read_bytes()
    report_clock = clock
    clock = "2026-01-01T00:01:00+00:00"
    monkeypatch.setattr(shared_outputs, "copy_path_to_host", copy)
    monkeypatch.setattr(writer, "index_output_artifacts", index)
    result = intake.invoke("company_report_writer", {"previous": evidence}, config=config, model=model)
    assert receipt_path.read_bytes() == receipt_bytes
    for name in ("research_coverage.json", "method_coverage.json", "company_index.json"):
        assert intake.store.read_path(name)["generated_at"] == report_clock
        assert (intake.root / "output" / name).read_bytes() == intake.store.path(name).read_bytes()
    assert intake.store.read_path("watch_state.json")["updated_at"] == report_clock
    assert model.calls == 1
    assert intake.invoke("company_report_writer", {"previous": evidence}, config=config, model=model) == result
    assert model.calls == 1


@pytest.mark.parametrize("role", ["company_report_writer", "batch_index_writer"])
def test_source_publication_retry_reuses_catalog_without_reindexing(intake, monkeypatch, role):
    config, model = publication_config(intake), PlanningModel()
    evidence = audited(intake, config)
    if role == "batch_index_writer":
        evidence = intake.invoke("company_report_writer", {"previous": evidence}, config=config, model=model)
    module = importlib.import_module("domain." + role)
    publish = module.freeze_file_publication
    def interrupted(block, produce, *, name):
        publication = publish(block, produce, name=name)
        if name.endswith("-sources"):
            raise OSError("synthetic interruption after source receipts")
        return publication
    monkeypatch.setattr(module, "freeze_file_publication", interrupted)
    with pytest.raises(OSError, match="after source receipts"):
        intake.invoke(role, {"previous": evidence}, config=config, model=model)
    calls = model.calls
    monkeypatch.setattr(module, "freeze_file_publication", publish)
    monkeypatch.setattr(module, "index_output_artifacts", lambda *_a: pytest.fail("Retry indexed source subjects again"))
    result = intake.invoke(role, {"previous": evidence}, config=config, model=model)
    assert intake.invoke(role, {"previous": evidence}, config=config, model=model) == result
    assert model.calls == (calls + 1 if role == "company_report_writer" else calls)
    published = intake.store.read(result)["published_files"]
    catalog = published["files"]["context_sources/outputs.json"]
    assert (intake.root / "output/context_sources/outputs.json").read_bytes() == intake.store.read_bytes(catalog)


def test_batch_delivery_failure_reuses_review_and_frozen_report_bytes(intake, monkeypatch):
    from mn_sdk.blueprint_support import shared_outputs
    config, model = publication_config(intake), PlanningModel()
    evidence = audited(intake, config)
    companies = intake.invoke("company_report_writer", {"previous": evidence}, config=config, model=model)
    copy = shared_outputs.copy_path_to_host
    def interrupted(source, target):
        if Path(target).name == "final_artifact.json":
            raise OSError("synthetic report delivery interruption")
        return copy(source, target)
    monkeypatch.setattr(shared_outputs, "copy_path_to_host", interrupted)
    with pytest.raises(OSError, match="delivery interruption"):
        intake.invoke("batch_index_writer", {"previous": companies}, config=config, model=model)
    assert model.calls == 2
    prepared = next(intake.store.run_dir.glob("blocks/*/prepared-batch.json"))
    artifact = json.loads(prepared.read_text())["data"]["artifact"]
    monkeypatch.setattr(shared_outputs, "copy_path_to_host", copy)
    result = intake.invoke("batch_index_writer", {"previous": companies}, config=config, model=model)
    assert intake.store.read_path("final_artifact.json") == artifact
    assert model.calls == 2
    assert intake.invoke("batch_index_writer", {"previous": companies}, config=config, model=model) == result
    published = intake.store.read(result)["published_files"]
    intake.store.path(published["files"]["final_artifact.json"]["path"]).write_bytes(b"tampered")
    with pytest.raises(RuntimeError, match="mismatch"):
        intake.invoke("batch_index_writer", {"previous": companies}, config=config, model=model)
    assert model.calls == 2


def test_native_intake_uses_explicit_staged_folder_without_runtime_context(intake):
    inputs = {"document_folder": None, "input_folder": str(intake.source.parent.parent)}
    first = intake.invoke("startup_folder_watcher", inputs)
    state = intake.store.read(intake.store.read(first)["state"])["data"]
    assert state["inputs"]["document_folder"] == str(intake.source.parent.parent)
    assert state["files"][0]["relative_path"] == "acme/pitch.txt"
    assert intake.invoke("startup_folder_watcher", inputs) == first
    assert not intake.store.path("workflow_state/runtime_context.json").exists()
