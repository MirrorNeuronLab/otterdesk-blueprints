from __future__ import annotations

from mn_sdk.step_runtime import StepContext

from mn_blueprint_support import get_actor_llm_client, resolve_actor_specs, run_actor_reviews

import run_blueprint as runtime
from ._shared import previous_payload, runtime_inputs, step_result


def run(context: StepContext) -> dict:
    config, inputs, _input_source = runtime_inputs(context)
    previous = previous_payload(context)
    llm_config = config.get("llm") if isinstance(config.get("llm"), dict) else {}
    quick = str(llm_config.get("mode") or "live").lower() in {"fake", "mock"} or bool((config.get("execution") or {}).get("quick_test"))
    sources, web_warnings = runtime.research_public_sources(previous.get("research_queries") or [], config, quick_test=quick)
    documents = previous.get("documents") or []
    evidence = runtime.deterministic_evidence(inputs, documents, sources)
    deterministic = runtime.deterministic_recommendation(evidence, sources)
    llm = get_actor_llm_client(config, None)
    recommendation = runtime.ask_llm_for_recommendation(llm, inputs, evidence, previous.get("rag") or {}, deterministic)
    actor_findings = run_actor_reviews(
        config=config,
        llm=llm,
        actor_ids=list(resolve_actor_specs(config).keys()),
        state={},
        task=runtime.load_prompt("purchase-review-task.md"),
        context={"inputs": inputs, "intake_plan": previous.get("intake_plan") or {}, "evidence": evidence, "recommendation": recommendation, "rag": previous.get("rag") or {}, "sources": sources},
    )
    payload = {
        **previous,
        "inputs": inputs,
        "sources": sources,
        "web_warnings": web_warnings,
        "evidence": evidence,
        "recommendation": recommendation,
        "actor_findings": actor_findings,
        "llm_usage": runtime.llm_usage(llm),
    }
    return step_result(context, payload, source_count=len(sources))
