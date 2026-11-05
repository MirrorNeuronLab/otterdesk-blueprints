"""Opt-in current OtterDesk consumers against an isolated native context engine."""

from contextlib import contextmanager
import importlib
import hashlib
import json
import os
from pathlib import Path
import sys
import pytest
from workspace_paths import companion_workspace

BLUEPRINTS = Path(__file__).resolve().parents[1]
WORKSPACE = companion_workspace(BLUEPRINTS)
pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_OTTERDESK_NATIVE_CONTEXT_TESTS") != "1",
    reason="enable RUN_OTTERDESK_NATIVE_CONTEXT_TESTS for isolated Rust integration",
)


@pytest.fixture(scope="module")
def native(tmp_path_factory):
    from mn_context_benchmark.tasks.services import OwnedServices

    parent = (
        Path(os.environ["OTTERDESK_TEST_RESULTS_DIR"])
        if os.environ.get("OTTERDESK_TEST_RESULTS_DIR")
        else tmp_path_factory.mktemp("otterdesk-native-context")
    )
    root = parent / "blueprint-runtime-context"
    root.mkdir(parents=True, exist_ok=False)
    with OwnedServices(
        WORKSPACE / "Membrane/mn-context-engine", root / "runtime"
    ) as services:
        yield root, services


@contextmanager
def payload(blueprint):
    prefixes = ("domain", "agents", "steps", "runtime")

    def selected(name):
        return any(name == p or name.startswith(p + ".") for p in prefixes)

    previous = {k: v for k, v in sys.modules.items() if selected(k)}
    paths = sys.path[:]
    for k in previous:
        sys.modules.pop(k)
    sys.path.insert(0, str(BLUEPRINTS / blueprint / "payloads"))
    for repository in ("mn-skills", "mn-agents"):
        sys.path.extend(str(p) for p in (WORKSPACE / repository).glob("*/src"))
    sys.path.extend(
        str(p) for p in (WORKSPACE / "mn-python-sdk/packages").glob("*/src")
    )
    sys.path.append(str(WORKSPACE / "Membrane/mn-context-source-code/src"))
    try:
        yield
    finally:
        for k in list(sys.modules):
            if selected(k):
                sys.modules.pop(k)
        sys.modules.update(previous)
        sys.path[:] = paths


def bind(monkeypatch, services, run):
    monkeypatch.setenv("MN_CONTEXT_ADDR", services.addresses["deterministic"])
    monkeypatch.setenv("MN_CONTEXT_AUTH_TOKEN", services.token)
    monkeypatch.setenv("MN_JOB_ID", "context-regression-job")
    monkeypatch.setenv("MN_RUN_ID", run)
    monkeypatch.delenv("MN_WORKFLOW_RUN_ID", raising=False)


def authored_fields(body):
    """Evaluator-only decoding of the current whole authored Facts contract."""
    assert isinstance(body, str) and body.startswith("# ")
    lines = body.splitlines()
    row = lines.index("## Facts") + 2
    columns = [cell.strip() for cell in lines[row].strip("|").split("|")]
    values = [json.loads(cell.strip()) for cell in lines[row + 2].strip("|").split("|")]
    return dict(zip(columns, values, strict=True))


def test_vc_actual_prompt_preserves_query_results_and_selected_external_passages(
    native, monkeypatch
):
    root, services = native
    bind(monkeypatch, services, "vc-current")
    from mn_context_benchmark.vc_context.dataset import load

    _, _, captures = load()
    run_dir = root / "vc-run"
    from mn_blueprint_blocks.context import BlockContext
    from mn_sdk_common.committed_artifacts import CommittedJsonStore
    from native_context_fixtures import vc_runtime_state

    # Historical replay stays frozen in the benchmark package. This current
    # consumer gate uses explicit synthetic outcomes, never a disposable run.
    state = vc_runtime_state(run_dir, [c["context"]["agent_id"] for c in captures])
    store = CommittedJsonStore(run_dir)
    rows = []
    with payload("vc_assistant"):
        memory = importlib.import_module("domain.text_memory")
        review = importlib.import_module("domain.review")
        config = {
            "text_memory": {
                "enabled": True,
                "max_results": 3,
                "max_context_bytes": 8192,
            }
        }
        for capture in captures:
            context = dict(capture["context"])
            # Controlled retrieved response: not a fabricated captured browser
            # outcome, and not the external corpus. Tests isolate composition.
            context["rag_context"] = {
                "status": "ready",
                "context": "Methodology requires source-qualified claims and explicit evidence gaps.",
                "citations": [{"ref": 1, "source": "controlled-methodology-response"}],
            }
            block = BlockContext(
                store=store,
                invocation_id="native-review-" + context["agent_id"],
                revision="synthetic-vc-state-v1",
                config=config,
                job_id="context-regression-job",
                run_id="vc-current",
                step_id=context["workflow_step_id"],
                agent_id=context["agent_id"],
            )
            context = memory.snapshot_memory_context(
                block, state, context, role=context["agent_id"]
            )
            witness = store.read(state["memory_witnesses"][context["agent_id"]])
            assert witness["packet"] == context["runtime_memory"]
            assert witness["inputs"] and witness["receipt"]
            packet = context["runtime_memory"]
            assert (
                packet["evidence"]
                and len(
                    json.dumps(
                        packet, ensure_ascii=False, separators=(",", ":")
                    ).encode()
                )
                <= 8192
            )
            fields = [authored_fields(r["content"]) for r in packet["evidence"]]
            assert any(
                r.get("runtime_kind") == "tool"
                and r.get("agent_id") == context["agent_id"]
                and r.get("status") == "failed"
                and r.get("qualification")
                == "recorded_tool_outcome_not_external_confirmation"
                for r in fields
            )
            families = {
                "company_identity_researcher": {"team", "product"},
                "funding_researcher": {"finance"},
                "traction_verifier": {"traction"},
            }.get(context["agent_id"])
            if families:
                assert all(
                    r["claim_family"] in families
                    for r in fields
                    if r.get("runtime_kind") == "claim"
                )
            system, prompt = review.build_actor_review_prompt(
                actor_id=context["agent_id"],
                actor_spec=capture["actor_spec"],
                context=context,
                knowledge_rag=context.get("knowledge_rag"),
            )
            assert prompt["context"]["runtime_memory"] == packet
            assert prompt["context"]["rag_context"] == context["rag_context"]
            assert prompt["available_rag_refs"] == context["rag_context"]["citations"]
            assert "fixture_witness" not in json.dumps(prompt)
            rows.append(
                {
                    "actor": context["agent_id"],
                    "input_origin": "synthetic-runtime-observations-v1",
                    "selected": len(packet["evidence"]),
                    "omitted": len(witness["receipt"]["selection"]["omitted"]),
                    "request": {
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": json.dumps(prompt)},
                        ]
                    },
                }
            )
    (root / "vc-current-prompts.json").write_text(json.dumps(rows, indent=2))


def test_cctv_caption_and_image_history_is_scoped_across_runs(native, monkeypatch):
    from datetime import datetime, timedelta, timezone
    from native_context_fixtures import CAMERA_JPEG, CameraEmbeddings

    root, services = native
    bind(monkeypatch, services, "cctv-first")
    config = {"source_context": {"enabled": True}}
    instant = datetime(2026, 11, 1, 12, tzinfo=timezone.utc)
    jpeg = CAMERA_JPEG

    with payload("cctv_operator"):
        store_type = importlib.import_module("domain.caption_store").CaptionStore
        history_type = importlib.import_module("domain.visual_history").VisualHistory
        store = store_type(
            root / "camera.db", job_id="camera-job", run_id="first", source_id="door"
        )
        embeddings = CameraEmbeddings()
        history = history_type(config, store, embeddings=embeddings)
        assert history.search("sampled activity", "", "")["observations"] == []

        def save(target, identity, seconds, *, image=False):
            start = instant + timedelta(seconds=seconds)
            caption = {
                "id": identity,
                "run_id": target.run_id,
                "start_time": start.isoformat(),
                "end_time": (start + timedelta(seconds=4)).isoformat(),
                "source_refs": [f"captions/{identity}.json"],
                "content": "Synthetic sampled activity " + identity,
            }
            if image:
                caption["snapshot"] = {
                    "received_at": (start + timedelta(seconds=1)).isoformat(),
                    "sha256": hashlib.sha256(jpeg).hexdigest(),
                }
            target.append(caption, jpeg if image else None)
            return caption

        saved = [save(store, "before-window", -10), save(store, "after-window", 120)]
        saved += [save(store, f"inside-{i}", i * 10, image=i == 1) for i in range(1, 4)]
        for _ in saved:
            assert history.index_next()
        assert not history.index_next()
        assert store.index_counts(history.model) == (5, 5)
        save(store, "pending", 40)

        other = store_type(
            store.path, job_id="camera-job", run_id="first", source_id="other-camera"
        )
        save(other, "OTHER_CAMERA_PRIVATE", 20, image=True)
        assert history_type(config, other, embeddings=embeddings).index_next()
        foreign = store_type(
            root / "foreign.db", job_id="other-job", run_id="first", source_id="door"
        )
        save(foreign, "OTHER_JOB_PRIVATE", 20, image=True)
        assert history_type(config, foreign, embeddings=embeddings).index_next()

        reopened = store_type(
            store.path, job_id="camera-job", run_id="second", source_id="door"
        )
        assert reopened.history(current_run=True)["observations"] == []
        chronology = reopened.history(limit=3)
        assert [c["id"] for c in chronology["observations"]] == [
            "inside-3",
            "pending",
            "after-window",
        ]
        assert chronology["omitted_count"] == 3
        current = history_type(config, reopened, embeddings=embeddings)
        packet = current.search(
            "sampled activity",
            instant.isoformat(),
            (instant + timedelta(minutes=1)).isoformat(),
        )
        assert packet["total"] == 4 and packet["indexed"] == 3
        assert {c["id"] for c in packet["observations"]} == {
            "inside-1",
            "inside-2",
            "inside-3",
        }
        assert all(c["run_id"] == "first" for c in packet["observations"])
        assert "OTHER_CAMERA_PRIVATE" not in json.dumps(packet)
        assert "OTHER_JOB_PRIVATE" not in json.dumps(packet)
        image = next(c for c in packet["observations"] if c["id"] == "inside-1")
        assert image["matched_via"] == "image"
        assert image["source_refs"] == ["captions/inside-1.json"]
        assert (
            image["snapshot"]["sha256"]
            == hashlib.sha256(reopened.frame("inside-1")).hexdigest()
        )
        (root / "cctv-current-history.json").write_text(
            json.dumps(
                {
                    "packet": packet,
                    "chronology": chronology,
                    "scope": "Synthetic captions, JPEG and fixed vectors; real native source indexing and retrieval. No model-quality or camera-coverage claim.",
                },
                indent=2,
            )
        )


@pytest.mark.parametrize("stage", ["plan", "assessment", "review"])
def test_litigation_current_decision_boundary_uses_native_passages_and_separate_guidance(
    native, monkeypatch, stage
):
    from mn_sdk.text_memory import runtime_text_memory

    root, services = native
    run = "litigation-consumer-" + stage
    bind(monkeypatch, services, run)
    config = json.loads(
        (BLUEPRINTS / "litigation_analyst/config/default.json").read_text()
    )
    scope = {"job_id": "context-regression-job", "run_id": run}
    memory = runtime_text_memory(config, principal="round-specialists", scope=scope)
    from mn_context_engine_sdk.intelligent_system import RuntimeRecord

    memory.record(
        RuntimeRecord(
            "prior-review",
            "Prior qualified review",
            "2026-10-04T10:00:00Z",
            "inferred_not_case_evidence",
            {"memory_family": "litigation_review"},
            notes="CaseN47 runtime finding: approval was not established; verify original invoices.",
            kind="decision",
        ),
        event_id="prior-review",
    )
    memory.close()
    calls = []

    class BoundaryRecorder:
        def completion_text(self, system, prompt):
            calls.append(json.loads(prompt))
            return '{"decision":"review"}'

    frozen = {
        "config": config,
        "memory_scope": scope,
        "payload": {"goal": "CaseN47 verify approval"},
    }
    with payload("litigation_analyst"):
        model = importlib.import_module("domain.round_model")
        model.complete(
            root / run,
            frozen,
            "probe",
            stage,
            "Return a bounded review decision.",
            {"goal": frozen["payload"]["goal"]},
            {
                "type": "object",
                "required": ["decision"],
                "properties": {"decision": {"type": "string"}},
                "additionalProperties": False,
            },
            client=BoundaryRecorder(),
        )
    assert len(calls) == 1
    assert calls[0]["guidance"]["retrieval"] == "lexical_fts5"
    assert calls[0]["guidance"]["citations"] and all(
        c["text"] for c in calls[0]["guidance"]["citations"]
    )
    receipt_path = root / run / "case/rounds/models/probe.memory.json"
    if stage == "plan":
        assert any(
            "approval was not established" in e["content"]
            for e in calls[0]["runtime_memory"]["evidence"]
        )
        receipt = json.loads(receipt_path.read_text())
        assert (
            receipt["receipt"]["retrieval"]["witness"]["stages"][0]["execution"][
                "backend"
            ]
            == "direct_markdown"
        )
        assert all(
            receipt["receipt"]["citations"][e["citation"]][0]["record_revision"]
            for e in calls[0]["runtime_memory"]["evidence"]
        )
    else:
        assert "runtime_memory" not in calls[0]
        assert "approval was not established" not in json.dumps(calls[0])
        assert not receipt_path.exists()
    (root / (run + "-boundary.json")).write_text(
        json.dumps(
            {
                "request": calls[0],
                "scope": "Injected answer recorder; native retrieval and actual prompt only, no answer-quality claim.",
            },
            indent=2,
        )
    )


def test_architecture_current_catalog_uses_native_source_passages_and_honest_graph_coverage(
    native, monkeypatch
):
    from mn_context_benchmark.specialist_context.needle import corpus

    root, services = native
    bind(monkeypatch, services, "architecture-consumer")
    config = json.loads(
        (BLUEPRINTS / "software_architecture_advisor/config/default.json").read_text()
    )
    # This native CPU gate exercises the supported lexical profile. The shipping
    # hybrid default requires a separately gated real embedding provider.
    config["source_search"] = {"mode": "lexical"}
    request = {
        "retrieval_config": config,
        "memory_scope": {
            "job_id": "context-regression-job",
            "run_id": "architecture-consumer",
        },
        "snapshot": "nativeconsumer",
        "goal": "CaseN47 inspect retry risk",
    }
    sources = {
        id + ".md": {"text": text, "sha256": hashlib.sha256(text.encode()).hexdigest()}
        for id, text in corpus("software_architecture_advisor")[0]
    }
    snapshot = {
        "snapshot_id": "nativeconsumer",
        "manifest": {"modules": {}},
        "sources": sources,
    }
    with payload("software_architecture_advisor"):
        module = importlib.import_module("domain.catalog_retrieval")
        monkeypatch.setattr(
            importlib.import_module("domain.source_embeddings"),
            "SourceEmbeddings",
            lambda *args, **kwargs: pytest.fail(
                "CPU consumer gate attempted model preparation"
            ),
        )
        store = importlib.import_module("domain.catalog_store").CatalogStore(
            root / "architecture-consumer"
        )
        module.publish_inputs(store, request, snapshot)
        result, evidence = module.retrieve(
            store,
            {"request": request},
            snapshot,
            {"task_id": "needle-review", "kind": "source_scan", "path": "module-a.md"},
            {"specs": {}},
        )
        assert not store.path("catalog/memory-context/needle-review.json").exists()
        source_receipt = store.read("catalog/source-context/needle-review.json")
    assert "runtime_memory" not in result
    assert any("CaseN47" in e["excerpt"] for e in evidence)
    assert source_receipt["compiled"]["bundles"]
    assert result["architecture_graph"]["status"] == "entity_unresolved"
    assert result["architecture_graph"]["incomplete"]
    assert not result["architecture_graph"]["queries"]
    assert result["source_query"]["selected_spans"] == len(evidence)
    (root / "architecture-consumer-boundary.json").write_text(
        json.dumps(
            {
                "context": result,
                "evidence": evidence,
                "scope": "Actual separate-source consumer with the supported lexical CPU profile. Original bodies are excluded from runtime recall. Missing structural snapshot is explicit; separate needle receipts prove DuckDB graph execution.",
            },
            indent=2,
        )
    )


def test_architecture_frozen_sources_and_prompt_assembly_at_paired_allowances(
    native, monkeypatch
):
    """Keep failed quality rows: completion proves measurement, not accuracy."""
    from mn_context_benchmark.cross_datatype.dataset import load
    from mn_context_benchmark.cross_datatype.blueprint_fixture import DEFAULT
    from mn_sdk.text_memory import runtime_text_memory
    from mn_sdk.source_query import source_text_query

    root, services = native
    _, manifest, sources, queries, gold = load(DEFAULT, "full", all_datatypes=False)
    snapshot = {
        "snapshot_id": "frozen-architecture-workload",
        "manifest": {"modules": {}},
        "sources": {
            s["source_ref"]: {"text": s["text"], "sha256": s["sha256"]}
            for s in sources.values()
            if s.get("blueprint_id") == "software_architecture_advisor"
        },
    }
    queries = [
        q for q in queries if q.get("blueprint_id") == "software_architecture_advisor"
    ]
    assert len(queries) == 80
    rows = []
    with payload("software_architecture_advisor"):
        retrieval = importlib.import_module("domain.catalog_retrieval")
        store_type = importlib.import_module("domain.catalog_store").CatalogStore
        prompts = importlib.import_module("domain.review_prompts")
        for budget in (8192, 32768):
            bind(monkeypatch, services, "architecture-paired-" + str(budget))
            store = store_type(root / ("architecture-paired-" + str(budget)))
            config = {
                "text_memory": {
                    "enabled": True,
                    "max_results": 6,
                    "max_context_bytes": budget,
                }
            }
            request = {
                "retrieval_config": config,
                "memory_scope": {
                    "job_id": "context-regression-job",
                    "run_id": "architecture-paired-" + str(budget),
                },
                "snapshot": snapshot["snapshot_id"],
                "goal": "Inspect exact frozen repository source.",
            }
            saved = {"request": request}
            retrieval.publish_inputs(store, request, snapshot)
            store.finish(
                "controlled-history",
                {
                    "task_id": "controlled-history",
                    "kind": "aspect_analysis",
                    "aspect_id": "frozen-source-replay",
                    "status": "completed",
                    "conclusion": "Controlled historical navigation; execution remains unknown.",
                    "limitations": ["No answer model ran in this diagnostic."],
                    "claims": [],
                    "observations": [],
                },
            )
            retrieval.publish_runtime_notes(store, saved)
            for query in queries:
                task = {
                    "task_id": query["id"],
                    "kind": "aspect_analysis",
                    "aspect_id": "frozen-source-replay",
                    "reason": query["query"],
                }
                packet, evidence = retrieval.retrieve(
                    store, saved, snapshot, task, {"specs": {}}
                )
                rendered = None
                admission_error = None
                try:
                    rendered = prompts.build_prompt(
                        task,
                        {"specs": {}, "conventions": ""},
                        snapshot,
                        {},
                        {},
                        budget,
                        {},
                        retrieval=packet,
                        graph_evidence=evidence,
                    )
                except ValueError as exc:
                    # Mandatory source groups are atomic. Capacity refusal is a
                    # measured failure, never permission to trim source support.
                    if (
                        str(exc)
                        != "Prompt budget cannot fit mandatory specification and output contract"
                    ):
                        raise
                    admission_error = str(exc)
                prompt = (
                    json.loads(rendered["prompt"])
                    if rendered
                    else {
                        "evidence": [],
                        "omissions": {"admission": "insufficient_capacity"},
                        "runtime_memory": {
                            "evidence": [],
                            "status": "insufficient_capacity",
                        },
                    }
                )
                retrieved = "\n".join(e["excerpt"] for e in evidence)
                visible = "\n".join(e["excerpt"] for e in prompt["evidence"])
                expected = gold[query["id"]]["gold_spans"]
                row = {
                    "id": query["id"],
                    "budget_bytes": budget,
                    "admission_status": "admitted"
                    if rendered
                    else "insufficient_capacity",
                    "admission_error": admission_error,
                    "retrieval_pass": all(s["quote"] in retrieved for s in expected),
                    "model_visible_pass": all(s["quote"] in visible for s in expected),
                    "retrieved_source_bytes": len(retrieved.encode()),
                    "model_visible_source_bytes": len(visible.encode()),
                    "rendered_prompt_bytes": len(rendered["prompt"].encode())
                    if rendered
                    else None,
                    "omissions": prompt["omissions"],
                    "runtime_memory": prompt["runtime_memory"],
                    "source_status": packet["source_query"]["status"],
                }
                if rendered:
                    assert row["rendered_prompt_bytes"] <= budget
                assert all(
                    e["excerpt"] in snapshot["sources"][e["path"]]["text"]
                    for e in prompt["evidence"]
                )
                receipt = store.read("catalog/memory-context/" + query["id"] + ".json")
                assert (
                    receipt["receipt"]["retrieval"]["witness"]["stages"][0][
                        "execution"
                    ]["backend"]
                    == "duckdb_constrained_sql"
                )
                assert packet["runtime_memory"]["evidence"]
                assert all(
                    e["content"].startswith("# Architecture review ")
                    for e in packet["runtime_memory"]["evidence"]
                )
                store.write(
                    "manual-review/" + query["id"] + ".json",
                    {
                        "query": query,
                        "expected_spans_evaluator_only": expected,
                        "row": row,
                        "retrieval": packet,
                        "request": rendered,
                    },
                )
                rows.append(row)
            source = source_text_query(
                config,
                principal="architecture-source-query",
                scope=request["memory_scope"],
            )
            memory = runtime_text_memory(
                config, principal="architecture", scope=request["memory_scope"]
            )
            try:
                assert (
                    source.client.verify()["verified"]
                    and memory.client.verify()["verified"]
                )
                assert source.scope["job_id"] != memory.scope["job_id"]
                outsider = source_text_query(
                    config, principal="architecture", scope=request["memory_scope"]
                )
                try:
                    entry = store.read("catalog/source-inputs.json")["catalog"][
                        "sources"
                    ][0]
                    with pytest.raises(Exception):
                        outsider.read_source(
                            {
                                "source_id": entry["source_id"],
                                "revision": entry["revision"],
                                "scope": outsider.scope,
                            }
                        )
                finally:
                    outsider.close()
            finally:
                source.close()
                memory.close()
    assert all(
        any(
            r["retrieval_pass"] and r["model_visible_pass"]
            for r in rows
            if r["budget_bytes"] == budget
        )
        for budget in (8192, 32768)
    )
    (root / "architecture-paired-assessment.json").write_text(
        json.dumps(
            {
                "schema": "mn.context.architecture_production_paired.v1",
                "rows": rows,
                "fixture_manifest_sha256": hashlib.sha256(
                    json.dumps(manifest, sort_keys=True).encode()
                ).hexdigest(),
                "scope": "Actual production retrieval and prompt builder on 80 frozen source questions. Bounded aspect task envelopes isolate evidence admission; full aspect specifications and deployed workflows are not evaluated.",
                "generation_calls": 0,
                "embedding_calls": 0,
                "serving_tokens": None,
                "answer_quality": None,
                "summaries": {
                    str(b): {
                        "cases": 80,
                        "retrieval_pass": sum(
                            r["retrieval_pass"] for r in rows if r["budget_bytes"] == b
                        ),
                        "model_visible_pass": sum(
                            r["model_visible_pass"]
                            for r in rows
                            if r["budget_bytes"] == b
                        ),
                        "insufficient_capacity": sum(
                            r["admission_status"] == "insufficient_capacity"
                            for r in rows
                            if r["budget_bytes"] == b
                        ),
                    }
                    for b in (8192, 32768)
                },
            },
            indent=2,
        )
    )
