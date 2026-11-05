"""Prospective paired quality-policy trial over real RPCs and a pinned worker.

No production deployment. Public questions/ingestion metadata select sources;
frozen gold is used only after retrieval and generation. Runtime fault controls
are explicitly separate from public source questions.
"""

import argparse
import hashlib
import importlib
import json
from pathlib import Path
import sys
import time

from mn_system_tests.benchmarks.quality_requests import request


def legacy_search(corpus, prompt, sources=(), limit=6):
    """Pre-quality source search, captured before this experiment (2026-10-05).

    Only identity binding differs from the candidate's search. Hydration and
    dependency grouping call the same production implementation in both arms.
    """
    from mn_context_engine_sdk.intelligent_system.sources import RankedSourceAdapter
    from mn_context_engine_sdk.intelligent_system.source_selection import (
        bounds,
        compile_roots,
    )

    scope = corpus._query_scope(prompt, sources, strict=True)
    roots = []
    for source_id, source in scope.items():
        adapter = source["adapter"]
        if adapter is not None and not isinstance(adapter, RankedSourceAdapter):
            roots.extend(
                (source_id, section)
                for section in adapter.locate(prompt, source["sections"])
            )
    discovery = {"strategy": "explicit_structural_binding", "unresolved": []}
    if not roots and scope:
        found = corpus.units.discover(
            prompt, sources=list(scope), mode="lexical", limit=limit, candidate_limit=32
        )
        discovery = {
            "strategy": "whole_unit_lexical",
            "unresolved": found.get("unresolved", []),
            "discovery": found.get("witness", {}),
        }
        for candidate in found.get("candidates", []):
            for section in scope[candidate["source_id"]]["sections"]:
                if bounds(scope[candidate["source_id"]], section) == (
                    candidate["start_byte"],
                    candidate["end_byte"],
                ):
                    roots.append((candidate["source_id"], section))
    discovery["unresolved"] += [
        "source_units_unavailable:" + s for s, v in scope.items() if not v["sections"]
    ]
    return compile_roots(corpus, prompt, roots, discovery)




def run(args):
    import grpc
    from mn_context_benchmark.cross_datatype.dataset import load as load_public
    from mn_context_benchmark.cross_datatype.blueprint_fixture import DEFAULT
    from mn_context_benchmark.cross_datatype.source_investigation.contracts import (
        load as load_source,
    )
    from mn_context_benchmark.cross_datatype.source_investigation.contracts import (
        base_request,
        task_prompt,
        grade,
        retention,
    )
    from mn_context_benchmark.cross_datatype.scoring import answer_score
    from mn_context_benchmark.cross_datatype.source_investigation.runner import visible
    from mn_context_benchmark.cross_datatype.engine import items
    from mn_context_benchmark.tasks.fixed_dataset import context_packet
    from mn_context_benchmark.tasks.models import (
        ModelClient,
        ServingTokenizer,
        answer,
        docker_json,
    )
    from mn_context_benchmark.tasks.services import OwnedServices
    from mn_context_engine_sdk import EvidenceClient
    from mn_context_engine_sdk.evidence import ContextRequirements, VerifiedCounter
    from mn_context_engine_sdk.intelligent_system import SourceCorpus, ContextAssembly
    from mn_context_source_code import PythonCodeAdapter

    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    sys.path.insert(0, str(args.blueprints / "litigation_analyst/payloads"))
    legal = importlib.import_module("domain.legal_sources").LegalSourceAdapter
    public_root, manifest, public, queries, gold = load_public(
        DEFAULT, "full", all_datatypes=False
    )
    source_root, source_manifest, source_data, source_tasks, source_gold = load_source()
    legal_tasks = [q for q in queries if q.get("blueprint_id") == "litigation_analyst"]
    # Fixed input order, every fourth question, chosen before any results.
    live_legal = {q["id"] for q in legal_tasks[::4]}
    protocol = {
        "version": "mn.context.quality_trial.v1",
        "allowances_utf8_bytes": [8192, 32768, 131072],
        "arms": ["no_memory", "current", "quality"],
        "legal_retrieval_cases": 80,
        "legal_answer_cases": sorted(live_legal),
        "source_answer_cases": [q["id"] for q in source_tasks],
        "runtime_control_cases": 8,
        "model": args.model,
        "digest": args.digest,
        "serving_tokens": 131072,
        "identical_request_reuse": "Only byte-identical complete requests share a response; reported explicitly. No retry or answer repair.",
        "retention_rule": "Fewer unsupported answers, preserve every baseline supported answer, no provenance/scope/budget regression.",
        "limits": "Runtime controls inject wrong/stale selection; not a natural error-rate estimate. Source fixtures are bounded diagnostics, not deployed workflow validation.",
    }
    (root / "protocol.json").write_text(json.dumps(protocol, indent=2) + "\n")
    report = {"protocol": protocol, "rows": [], "status": "running"}

    def save():
        (root / "report.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n"
        )

    save()
    worker = ModelClient(args.endpoint, timeout=180)
    counter = ServingTokenizer(args.digest)
    installed = docker_json("model", "list", "--json")
    if not any(
        m.get("id") == args.digest and args.model in m.get("tags", [])
        for m in installed
    ):
        raise ValueError("Pinned worker not installed")
    probe = request(args.model, "No evidence available.", [])
    measured = counter(probe)
    if counter.metadata["n_ctx"] != 131072:
        raise ValueError("Required 128K serving allocation is not active")
    response, seconds = worker.complete(probe)
    verified = VerifiedCounter.from_probe(
        counter,
        probe,
        response["usage"]["prompt_tokens"],
        model_version=args.digest,
        tokenizer_version=counter.metadata["build"],
        template_version=counter.metadata["template_sha256"],
    )
    report["preflight"] = {
        "tokenizer": counter.metadata,
        "input_tokens": measured,
        "response": response,
        "seconds": seconds,
    }
    save()
    responses = {}

    def generate(admission, row):
        if admission.status != "ready":
            row.update(blocked=True, abstain=True, supported=False, unsupported=False)
            return None
        payload = admission.request
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        row["request_hash"] = digest
        row["verified_tokens"] = admission.witness["token_accounting"]["input_tokens"]
        row["response_reused"] = digest in responses
        if digest not in responses:
            raw, latency = worker.complete(payload)
            if raw.get("usage", {}).get("prompt_tokens") != row["verified_tokens"]:
                raise ValueError("Provider and native tokenizer disagree")
            responses[digest] = (raw, latency)
            (root / (digest + ".json")).write_text(
                json.dumps({"request": payload, "response": raw}, indent=2)
            )
        raw, latency = responses[digest]
        row["generation_seconds"] = latency
        try:
            return answer(raw)
        except (ValueError, KeyError, TypeError) as error:
            row.update(
                error=type(error).__name__ + ": " + str(error),
                supported=False,
                unsupported=False,
                abstain=False,
            )
            return None

    with OwnedServices(
        args.workspace / "Membrane/mn-context-engine", root / "runtime"
    ) as services:
        with grpc.insecure_channel(services.addresses["deterministic"]) as channel:
            client = EvidenceClient(
                channel,
                job_id=root.name,
                run_id="evaluation",
                principal="benchmark",
                auth_token=services.token,
                timeout=120,
            )
            corpus = SourceCorpus(client)
            all_sources = {
                k: v
                for k, v in public.items()
                if v.get("blueprint_id") == "litigation_analyst"
            }
            all_sources.update(source_data)
            for ident, s in all_sources.items():
                path = s.get("source_ref") or s["path"]
                corpus.add(
                    s["text"],
                    source_id=ident,
                    path=path,
                    event_id=s["sha256"],
                    adapter=PythonCodeAdapter() if path.endswith(".py") else legal(),
                    aliases=(s["title"].strip(),) if s.get("title") else (),
                )
            corpus.units.register()
            tasks = [
                {**q, "cohort": "legal_public", "live": q["id"] in live_legal}
                for q in legal_tasks
            ]
            tasks += [
                {**q, "cohort": "source_interpretation", "live": True}
                for q in source_tasks
            ]
            legal_scope = [
                "job:" + s
                for s in public
                if public[s].get("blueprint_id") == "litigation_analyst"
            ]
            for number, task in enumerate(tasks):
                scope = (
                    legal_scope if task["cohort"] == "legal_public" else task["sources"]
                )
                for budget in protocol["allowances_utf8_bytes"]:
                    for arm in protocol["arms"]:
                        row = {
                            "id": task["id"],
                            "cohort": task["cohort"],
                            "domain": task.get("domain", "legal"),
                            "budget": budget,
                            "arm": arm,
                            "live": task["live"],
                        }
                        started = time.perf_counter()
                        try:
                            compiled = None
                            if arm == "current":
                                compiled = legacy_search(corpus, task["query"], scope)
                            elif arm == "quality":
                                compiled = corpus.search(
                                    task["query"],
                                    sources=scope,
                                    requirements=ContextRequirements(
                                        required_checks=(
                                            "source_binding",
                                            "support_complete",
                                        )
                                    ),
                                )
                            selected = []
                            if compiled is not None:
                                packet = context_packet(compiled, budget)
                                selected = items(compiled, packet)
                                compiled = {
                                    **compiled,
                                    "bundles": [
                                        b
                                        for b in compiled["bundles"]
                                        if b["bundle_id"] in packet["selected_bundles"]
                                    ],
                                }
                                if packet["status"] != "ready":
                                    compiled.update(status=packet["status"])
                                row["quality"] = compiled.get("quality")
                            row["retrieval_seconds"] = time.perf_counter() - started
                            row["selected_bytes"] = sum(
                                len(i["content"].encode()) for i in selected
                            )
                            if task["cohort"] == "legal_public":
                                expected = gold[task["id"]]
                                row["retained"] = all(
                                    any(
                                        i["handle"]["source_id"]
                                        == "job:" + s["document"]
                                        and s["quote"] in i["content"]
                                        for i in selected
                                    )
                                    for s in expected["gold_spans"]
                                )
                            else:
                                row["retained"] = retention(
                                    source_gold[task["id"]], selected
                                )["complete"]
                            if task["live"]:
                                if task["cohort"] == "source_interpretation":
                                    base = base_request(
                                        task, args.model, "source_supported_v6"
                                    )
                                    prompt = task_prompt(task, "source_supported_v6")
                                else:
                                    base = request(args.model, task["query"], [])
                                    base["messages"] = base["messages"][:1]
                                    prompt = task["query"]
                                kwargs = dict(
                                    base_request=base,
                                    prompt=prompt,
                                    counter=verified,
                                    input_limit=130048,
                                    serving_context_limit=131072,
                                    output_reserve=768,
                                )
                                admission = ContextAssembly().prepare(
                                    {"source": compiled} if compiled else {},
                                    requirements={"source": ContextRequirements()}
                                    if arm == "quality"
                                    else None,
                                    **kwargs,
                                )
                                row["admission_status"] = admission.status
                                value = generate(admission, row)
                                if value is not None:
                                    evidence = (
                                        visible(admission)
                                        if compiled and admission.status == "ready"
                                        else []
                                    )
                                    if task["cohort"] == "source_interpretation":
                                        grade_result = grade(
                                            task,
                                            source_gold[task["id"]],
                                            value,
                                            evidence,
                                            contract="source_supported_v6",
                                            citation_text=admission.citation_text,
                                        )
                                        row.update(
                                            grade=grade_result,
                                            supported=grade_result["success"],
                                            abstain=value.get("decision")
                                            == "insufficient_evidence",
                                            unsupported=bool(
                                                grade_result.get(
                                                    "unsupported_structured_facts", 0
                                                )
                                            )
                                            or any(
                                                v is not None
                                                and not grade_result.get(
                                                    "per_fact_support", {}
                                                ).get(k, False)
                                                for k, v in value.get(
                                                    "facts", {}
                                                ).items()
                                            ),
                                        )
                                    else:
                                        known = {i["evidence_id"]: i for i in evidence}
                                        cited = value.get("citations", [])
                                        correct = answer_score(
                                            expected["expected_answer"],
                                            value.get("answer"),
                                            expected.get("acceptable_answers", []),
                                        )["correct"]
                                        supported = (
                                            bool(cited)
                                            and all(c in known for c in cited)
                                            and all(
                                                any(
                                                    c in known
                                                    and known[c]["handle"]["source_id"]
                                                    == "job:" + s["document"]
                                                    and s["quote"]
                                                    in known[c]["content"]
                                                    for c in cited
                                                )
                                                for s in expected["gold_spans"]
                                            )
                                        )
                                        row.update(
                                            supported=bool(correct and supported),
                                            abstain=value.get("abstain") is True,
                                            unsupported=value.get("answer") is not None
                                            and not (correct and supported),
                                            answer=value,
                                        )
                        except Exception as error:
                            row.update(
                                error=type(error).__name__ + ": " + str(error),
                                supported=False,
                            )
                        report["rows"].append(row)
                        save()
                print(
                    json.dumps(
                        {"completed": number + 1, "total": len(tasks), "id": task["id"]}
                    ),
                    flush=True,
                )
            report["runtime_controls"] = (
                "Run separately: deterministic native packet fault controls, not public source accuracy."
            )
    report.update(
        status="completed",
        unique_generation_calls=len(responses),
        tokenizer=counter.metadata,
    )
    save()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--blueprints", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--digest", required=True)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    if not args.live:
        parser.error("--live is required to use the attached worker")
    sys.path.insert(0, str(args.workspace / "Membrane/mn-context-source-code/src"))
    run(args)


if __name__ == "__main__":
    main()
