"""Frozen litigation source questions through production collection/admission.

The answer recorder is injected. Native retrieval, ACLs, citations, typed table
and graph execution are real; this test does not measure answer correctness.
"""

import hashlib
import importlib
import json
import os
import shutil
from pathlib import Path

import pytest

from mn_context_benchmark.tasks.services import OwnedServices
from test_native_context_integration import WORKSPACE, BLUEPRINTS, payload, bind

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_OTTERDESK_NATIVE_CONTEXT_TESTS") != "1",
    reason="enable RUN_OTTERDESK_NATIVE_CONTEXT_TESTS for isolated Rust integration",
)


def test_litigation_frozen_questions_at_paired_allowances(monkeypatch, tmp_path):
    from mn_context_benchmark.cross_datatype.dataset import load
    from mn_context_benchmark.cross_datatype.blueprint_fixture import DEFAULT
    from mn_sdk.text_memory import runtime_text_memory
    from mn_sdk.source_query import source_text_query
    from mn_sdk_rag import EvidenceSpan

    root = (
        Path(os.environ["OTTERDESK_TEST_RESULTS_DIR"])
        if os.environ.get("OTTERDESK_TEST_RESULTS_DIR")
        else tmp_path
    ) / "litigation-original-context"
    root.mkdir(parents=True, exist_ok=False)
    code = []
    for repository, folder, suffix in [
        (WORKSPACE / "Membrane/mn-context-engine", "src", ".rs"),
        (WORKSPACE / "Membrane/mn-context-engine-python-sdk", "src", ".py"),
        (WORKSPACE / "mn-python-sdk", "mn_sdk", ".py"),
        (BLUEPRINTS / "litigation_analyst", "payloads", ".py"),
    ]:
        code.extend(
            (repository, path) for path in (repository / folder).rglob("*" + suffix)
        )
        code.extend(
            (repository, repository / name)
            for name in (
                "README.md",
                "SPEC.md",
                "pyproject.toml",
                "Cargo.toml",
                "Cargo.lock",
            )
            if (repository / name).is_file()
        )
    code.append((Path(__file__).parent, Path(__file__)))
    snapshot = {}
    for repository, path in code:
        name = repository.name + "/" + path.relative_to(repository).as_posix()
        target = root / "source-snapshot" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        snapshot[name] = hashlib.sha256(target.read_bytes()).hexdigest()
    (root / "source-snapshot.json").write_text(
        json.dumps(snapshot, sort_keys=True, indent=2)
    )
    _, manifest, sources, queries, gold = load(DEFAULT, "full", all_datatypes=False)
    sources = {
        id: s
        for id, s in sources.items()
        if s.get("blueprint_id") == "litigation_analyst"
    }
    queries = [q for q in queries if q.get("blueprint_id") == "litigation_analyst"]
    assert len(sources) == 6 and len(queries) == 80
    inputs = root / "inputs"
    inputs.mkdir()
    for source in sources.values():
        (inputs / (source["title"].strip() + ".txt")).write_text(source["text"])
    rows = []
    with (
        OwnedServices(
            WORKSPACE / "Membrane/mn-context-engine", root / "runtime"
        ) as services,
        payload("litigation_analyst"),
    ):
        intake = importlib.import_module("domain.intake")
        original = importlib.import_module("domain.source_query")
        tasks = importlib.import_module("domain.round_tasks")
        state = importlib.import_module("domain.round_state")
        EvidenceStore = importlib.import_module("domain.evidence.store").EvidenceStore
        EvidenceAssistant = importlib.import_module(
            "domain.evidence.assistant"
        ).EvidenceAssistant
        claims = importlib.import_module("domain.claim_memory")
        for budget in (8192, 32768):
            run = "litigation-paired-" + str(budget)
            bind(monkeypatch, services, run)
            config = json.loads(
                (BLUEPRINTS / "litigation_analyst/config/default.json").read_text()
            )
            config["text_memory"].update(max_context_bytes=budget, max_results=6)
            run_dir = root / run
            context = {
                "config": config,
                "run_dir": run_dir,
                "job_id": "context-regression-job",
                "run_id": run,
                "payload": {
                    "input_folder": str(inputs),
                    "goal": "Review selected contract clauses; preserve source qualifications and counterevidence.",
                },
            }
            intake.prepare_sources(context)
            case = run_dir / "case"
            corpus = intake.PreparedCorpus(case, "case")
            documents = {d.source_id: d for d in corpus.scan()}
            source_by_fixture = {
                id: next(
                    d.source_id
                    for d in documents.values()
                    if d.relative_path == source["title"].strip() + ".txt"
                )
                for id, source in sources.items()
            }
            store = EvidenceStore(case / "evidence.sqlite3")
            store.add_sources(corpus.scan())
            investigation = store.create_investigation(
                context["payload"]["goal"],
                "case",
                llm_model="injected-neutral-recorder",
                graph_path=case / "unused-observed-graph.rgx",
            )
            scope = {"job_id": "context-regression-job", "run_id": run}
            frozen = {
                "config": config,
                "payload": context["payload"],
                "memory_scope": scope,
                "investigation_id": investigation,
                "source_review_flags": {},
            }
            context_ref = state.save(run_dir, "case/rounds/context.json", frozen)
            for query in queries:
                retrieved = original.search(
                    case, corpus, config, scope, query["query"], 6
                )
                for span in retrieved["passages"]:
                    evidence = EvidenceSpan(**span, provenance_kind="observed")
                    EvidenceAssistant._validate_evidence(evidence, documents)
                    store.add_evidence(investigation, evidence)
                prefix = query["id"]
                task = {
                    "prefix": prefix,
                    "hypothesis": {
                        "id": prefix,
                        "question": query["query"],
                        "support_query": query["query"],
                        "counter_query": query["query"],
                        "graph_tools": [],
                        "expected_information": "Locate source statements; a ranked match does not establish a legal finding.",
                    },
                }
                task_ref = state.save(
                    run_dir, "case/rounds/" + prefix + "-task.json", task
                )
                state.save(
                    run_dir,
                    "case/rounds/" + prefix + "-evidence.json",
                    {
                        "hypothesis": task["hypothesis"],
                        "evidence_ids": [
                            s["evidence_id"] for s in retrieved["passages"]
                        ],
                        "records": [{"purpose": "support", "result": retrieved}],
                    },
                )
                calls = []

                class Recorder:
                    def completion_text(self, system, user):
                        request = json.loads(user)
                        calls.append({"system": system, "request": request})
                        return json.dumps(
                            {
                                "hypothesis": {
                                    "id": prefix,
                                    "question": query["query"],
                                    "factual_basis": "Diagnostic evidence admission only; no answer inference ran.",
                                    "supporting_evidence": [],
                                    "contradictory_evidence": [],
                                    "alternatives": [
                                        "The selected source units may omit decisive qualifications."
                                    ],
                                    "status": "inconclusive",
                                    "assessment": "No answer-quality conclusion in this diagnostic.",
                                    "outstanding_enquiries": [
                                        "Run a verified serving-worker evaluation."
                                    ],
                                    "parent_id": None,
                                },
                                "report": {
                                    "findings": [],
                                    "conclusion_ids": [],
                                    "follow_up": ["Review omitted evidence."],
                                },
                            }
                        )

                tasks.assess_hypothesis(
                    context,
                    {"context": context_ref, "task": task_ref},
                    llm_client=Recorder(),
                )
                assert len(calls) == 1
                visible = calls[0]["request"]["evidence"]
                expected = gold[query["id"]]["gold_spans"]

                def retained(spans):
                    return all(
                        any(
                            s["source_id"] == source_by_fixture[e["document"]]
                            and e["quote"] in s["text"]
                            for s in spans
                        )
                        for e in expected
                    )

                saved = state.read(run_dir / f"case/rounds/models/{prefix}-assess.json")
                packet = calls[0]["request"]["runtime_memory"]
                assert all(e["content"].startswith("# ") for e in packet["evidence"])
                assert all(
                    d.text not in e["content"]
                    for d in documents.values()
                    for e in packet["evidence"]
                )
                assert (
                    len(
                        json.dumps(
                            packet, ensure_ascii=False, separators=(",", ":")
                        ).encode()
                    )
                    <= budget
                )
                context_bytes = len(
                    json.dumps(visible, ensure_ascii=False).encode()
                ) + len(
                    json.dumps(
                        packet, ensure_ascii=False, separators=(",", ":")
                    ).encode()
                )
                assert context_bytes <= budget
                envelope = {
                    "model": "default",
                    "max_tokens": 2048,
                    "messages": [
                        {
                            "role": "system",
                            "content": calls[0]["system"]
                            + "\nReturn only one valid JSON object.",
                        },
                        {"role": "user", "content": json.dumps(calls[0]["request"])},
                    ],
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": {
                            "name": "litigation_stage",
                            "strict": True,
                            "schema": saved["schema"],
                        },
                    },
                }
                row = {
                    "id": prefix,
                    "allowance_bytes": budget,
                    "retrieval_pass": retained(retrieved["passages"]),
                    "model_visible_pass": retained(visible),
                    "retrieved_source_bytes": sum(
                        len(s["text"].encode()) for s in retrieved["passages"]
                    ),
                    "model_visible_source_bytes": sum(
                        len(s["text"].encode()) for s in visible
                    ),
                    "runtime_packet_bytes": len(
                        json.dumps(
                            packet, ensure_ascii=False, separators=(",", ":")
                        ).encode()
                    ),
                    "selected_context_bytes": context_bytes,
                    "request_json_bytes": len(
                        json.dumps(envelope, ensure_ascii=False).encode()
                    ),
                    "source_status": retrieved["status"],
                    "omitted_passages": calls[0]["request"]["omitted_passages"],
                    "runtime_status": packet["status"],
                }
                review = {
                    "query": query,
                    "expected_spans_evaluator_only": expected,
                    "row": row,
                    "retrieval": retrieved,
                    "request": envelope,
                }
                state.save(run_dir, "manual-review/" + prefix + ".json", review)
                rows.append(row)
            # A controlled support/opposition graph proves traversal on actual
            # authored locators. It makes no assertion about these clauses' truth.
            evidence = store.evidence_for(investigation)
            assert len(evidence) >= 2
            controlled = {
                "hypothesis": {
                    "id": "graph-probe",
                    "status": "inconclusive",
                    "question": "Controlled graph navigation probe; not a case finding.",
                    "supporting_evidence": [evidence[0].evidence_id],
                    "contradictory_evidence": [evidence[1].evidence_id],
                },
                "report": {"findings": []},
            }
            claims.publish(run_dir, frozen, "graph-probe", controlled)
            marker = state.read(case / "rounds/graph-probe-memory-graph.json")
            memory = runtime_text_memory(
                config, principal="round-specialists", scope=scope
            )
            source = source_text_query(
                config, principal="round-specialists", scope=scope
            )
            try:
                seed = marker["claim"]["source_id"].split(":", 1)[1]
                graph = memory.retrieve(
                    {
                        "query": "",
                        "limit": 20,
                        "stages": [
                            {
                                "mode": "graph",
                                "graph": {
                                    "seeds": [seed],
                                    "direction": "outgoing",
                                    "relations": [
                                        "SUPPORTED_BY",
                                        "OPPOSED_BY",
                                        "CITES",
                                    ],
                                    "max_hops": 2,
                                },
                            }
                        ],
                    }
                )
                assert {f["relation"] for f in graph["graph_facts"]} == {
                    "SUPPORTED_BY",
                    "OPPOSED_BY",
                    "CITES",
                }
                recent = memory.retrieve(
                    {
                        "query": "",
                        "limit": 3,
                        "stages": [
                            {
                                "mode": "analytical",
                                "analytical": {
                                    "operation": "recent",
                                    "timestamp_field": "timestamp",
                                    "limit": 3,
                                    "filters": [
                                        {
                                            "field": "memory_family",
                                            "op": "eq",
                                            "value": "litigation_review",
                                        }
                                    ],
                                },
                            }
                        ],
                    }
                )
                assert len(recent["computed"][0]) == 3
                assert (
                    recent["witness"]["stages"][0]["execution"]["backend"]
                    == "duckdb_constrained_sql"
                )
                assert (
                    memory.client.verify()["verified"]
                    and source.client.verify()["verified"]
                )
                assert memory.scope["job_id"] != source.scope["job_id"]
                outsider = source_text_query(config, principal="outsider", scope=scope)
                try:
                    reference = next(
                        iter(
                            state.read(case / "source-query.json")[
                                "source_records"
                            ].values()
                        )
                    )
                    with pytest.raises(Exception):
                        outsider.read_source({**reference, "scope": outsider.scope})
                finally:
                    outsider.close()
                state.save(
                    run_dir,
                    "manual-review/native-controls.json",
                    {
                        "graph": graph,
                        "recent": recent,
                        "source_acl_denied": True,
                        "separate_corpora": True,
                    },
                )
            finally:
                memory.close()
                source.close()
    assessment = {
        "schema": "mn.context.litigation_production_paired.v1",
        "rows": rows,
        "fixture_manifest_sha256": hashlib.sha256(
            json.dumps(manifest, sort_keys=True).encode()
        ).hexdigest(),
        "generation_calls": 0,
        "embedding_calls": 0,
        "serving_tokens": None,
        "answer_quality": None,
        "scope": "80 unchanged frozen CUAD questions through production original-source retrieval and actual assessor admission. Neutral answer recorder; no deployed workflow or worker-quality claim. The 2000-byte per-finding citation limit remains enforced. Source units and optional runtime navigation share a byte allowance; full request JSON bytes are reported separately and are not serving tokens.",
        "summaries": {
            str(b): {
                "cases": 80,
                "retrieval_pass": sum(
                    r["retrieval_pass"] for r in rows if r["allowance_bytes"] == b
                ),
                "model_visible_pass": sum(
                    r["model_visible_pass"] for r in rows if r["allowance_bytes"] == b
                ),
            }
            for b in (8192, 32768)
        },
    }
    (root / "assessment.json").write_text(json.dumps(assessment, indent=2))
