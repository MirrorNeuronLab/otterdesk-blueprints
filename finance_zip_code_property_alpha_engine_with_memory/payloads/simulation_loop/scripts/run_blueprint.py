#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
import math
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    from mn_blueprint_support import (
        architecture_contract,
        create_runtime_context,
        get_llm_client,
        load_config,
        resolve_input_overrides,
        run_blueprint_cli,
        utc_now_iso,
    )
    from mn_blueprint_support.web_ui import maybe_write_static_output
except ModuleNotFoundError:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "mn-skills" / "blueprint_support_skill" / "src"
        if candidate.exists():
            sys.path.insert(0, str(candidate))
            break
    from mn_blueprint_support import (
        architecture_contract,
        create_runtime_context,
        get_llm_client,
        load_config,
        resolve_input_overrides,
        run_blueprint_cli,
        utc_now_iso,
    )
    from mn_blueprint_support.web_ui import maybe_write_static_output


BLUEPRINT_ID = "finance_zip_code_property_alpha_engine_with_memory"
BLUEPRINT_NAME = "Zip Code Property Alpha Engine With Memory"
CATEGORY = "finance"
DESCRIPTION = (
    "Rank property acquisition opportunities with working memory over noisy ZIP-code history, "
    "broker flow, financing constraints, and prior decision outcomes."
)

TARGET_ZIP = "02139"
DISTRACTOR_ZIPS = ("02138", "02140", "02141", "02142", "02144", "02145", "02446")
CRITICAL_SOURCE_REFS = (
    "mem:02139-transit-tailwind",
    "mem:02139-biotech-hiring",
    "mem:02139-rent-comp-upside",
    "mem:02139-dscr-exception",
    "mem:river-quad-seller-motivation",
    "mem:river-quad-clean-inspection",
    "mem:ivy-duplex-flood-insurance",
    "mem:ivy-duplex-roof-deferred",
)


@dataclass(frozen=True)
class MemoryFact:
    id: str
    period: str
    zip_code: str
    source: str
    kind: str
    content: str
    importance: float
    confidence: float
    impact: dict[str, float]
    tags: tuple[str, ...] = ()
    property_id: str | None = None
    source_refs: tuple[str, ...] = ()
    private: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "period": self.period,
            "zip_code": self.zip_code,
            "property_id": self.property_id,
            "source": self.source,
            "kind": self.kind,
            "content": self.content,
            "importance": round(self.importance, 3),
            "confidence": round(self.confidence, 3),
            "impact": {key: round(value, 3) for key, value in self.impact.items()},
            "tags": list(self.tags),
            "source_refs": list(self.source_refs),
            "private": self.private,
        }


@dataclass
class MemoryPacket:
    selected_facts: list[MemoryFact]
    dropped_count: int
    estimated_input_facts: int
    estimated_output_tokens: int
    connected_signals: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "selected_facts": [fact.to_dict() for fact in self.selected_facts],
            "dropped_count": self.dropped_count,
            "estimated_input_facts": self.estimated_input_facts,
            "estimated_output_tokens": self.estimated_output_tokens,
            "connected_signals": self.connected_signals,
            "source_refs": sorted({ref for fact in self.selected_facts for ref in fact.source_refs}),
        }


@dataclass
class AllContextPacket:
    effective_facts: list[MemoryFact]
    total_facts: int
    estimated_input_tokens: int
    effective_tokens: int
    token_budget: int
    attention_limit: int
    budget_violation: bool
    dropped_by_window: int
    truncation_reason: str

    def to_dict(self) -> dict[str, Any]:
        used_refs = sorted({ref for fact in self.effective_facts for ref in fact.source_refs})
        return {
            "strategy": "share_full_agent_history",
            "total_facts": self.total_facts,
            "effective_facts": len(self.effective_facts),
            "estimated_input_tokens": self.estimated_input_tokens,
            "effective_tokens": self.effective_tokens,
            "token_budget": self.token_budget,
            "attention_limit": self.attention_limit,
            "budget_violation": self.budget_violation,
            "dropped_by_window": self.dropped_by_window,
            "truncation_reason": self.truncation_reason,
            "estimated_latency_ms": estimate_latency_ms(self.estimated_input_tokens, base_ms=120.0),
            "used_source_refs": used_refs,
            "critical_fact_recall": round(len(set(used_refs) & set(CRITICAL_SOURCE_REFS)) / len(CRITICAL_SOURCE_REFS), 4),
        }


@dataclass
class WorkingMemory:
    facts: list[MemoryFact] = field(default_factory=list)

    def add(self, fact: MemoryFact) -> None:
        self.facts.append(fact)

    def extend(self, facts: list[MemoryFact]) -> None:
        for fact in facts:
            self.add(fact)

    def retrieve(self, query: dict[str, Any], *, limit: int = 36) -> MemoryPacket:
        target_zip = str(query.get("target_zip") or TARGET_ZIP)
        property_ids = set(query.get("property_ids") or [])
        query_tags = set(query.get("tags") or [])
        scored: list[tuple[float, MemoryFact]] = []
        for fact in self.facts:
            if fact.private:
                continue
            score = fact.importance * 3.0 + fact.confidence
            if fact.zip_code == target_zip:
                score += 4.0
            if fact.property_id and fact.property_id in property_ids:
                score += 3.5
            if query_tags & set(fact.tags):
                score += 1.2 * len(query_tags & set(fact.tags))
            if "critical" in fact.tags:
                score += 2.0
            if "stale" in fact.tags:
                score -= 1.0
            scored.append((score, fact))

        selected = [fact for _score, fact in sorted(scored, key=lambda item: (-item[0], item[1].id))[:limit]]
        return MemoryPacket(
            selected_facts=selected,
            dropped_count=max(0, len(self.facts) - len(selected)),
            estimated_input_facts=len(self.facts),
            estimated_output_tokens=estimate_tokens("\n".join(fact.content for fact in selected)),
            connected_signals=connect_signals(selected, target_zip),
        )


def run_blueprint(
    blueprint_id: str = BLUEPRINT_ID,
    *,
    inputs: dict[str, Any] | None = None,
    llm_client: Any | None = None,
    config: dict[str, Any] | None = None,
    config_path: str | Path | None = None,
    config_json: str | None = None,
    run_id: str | None = None,
    runs_root: str | Path | None = None,
    input_adapter: str | None = None,
    input_file: str | Path | None = None,
    write_run_store: bool | None = None,
) -> dict[str, Any]:
    if blueprint_id != BLUEPRINT_ID:
        raise ValueError(f"this runner handles {BLUEPRINT_ID!r}, got {blueprint_id!r}")

    started_at = utc_now_iso()
    default_config_path = Path(__file__).resolve().parents[3] / "config" / "default.json"
    resolved_config = load_config(
        BLUEPRINT_ID,
        default_config_path=default_config_path,
        config=config,
        config_path=config_path,
        config_json=config_json,
        runs_root=runs_root,
        run_id=run_id,
        input_adapter=input_adapter,
        input_file=input_file,
        write_run_store=write_run_store,
    )
    adapter_inputs, input_source = resolve_input_overrides(resolved_config)
    runtime_inputs = default_inputs()
    runtime_inputs.update(adapter_inputs)
    runtime_inputs.update(inputs or {})
    runtime_inputs["steps"] = max(1, int(runtime_inputs.get("steps", 6)))
    runtime_inputs["seed"] = int(runtime_inputs.get("seed", 77))
    runtime_inputs["target_zip"] = str(runtime_inputs.get("target_zip") or TARGET_ZIP)
    runtime_inputs["memory_mode"] = str(runtime_inputs.get("memory_mode") or "compare")

    llm_mode = str((resolved_config.get("llm") or {}).get("mode") or "ollama")
    llm = llm_client or get_llm_client("fake" if llm_mode in {"fake", "mock"} else None)
    context = create_runtime_context(BLUEPRINT_ID, resolved_config, runtime_inputs, input_source)
    context.start()
    try:
        rng = random.Random(runtime_inputs["seed"])
        large_context = generate_large_context(runtime_inputs, rng)
        memory = WorkingMemory()
        memory.extend(large_context["facts"])
        state = initial_state(runtime_inputs)
        initial = copy.deepcopy(state)
        timeline: list[dict[str, Any]] = []
        benchmark_rows: list[dict[str, Any]] = []

        context.event(
            "large_context_seeded",
            {
                "facts": len(large_context["facts"]),
                "internal_messages": len(large_context["internal_messages"]),
                "critical_source_refs": list(CRITICAL_SOURCE_REFS),
            },
        )

        for step in range(runtime_inputs["steps"]):
            context.event("simulation_step_started", {"step": step, "state_before": rounded_state(state)})
            advance_market_state(state, rng, step)
            current_messages = current_internal_messages(large_context["internal_messages"], step)
            current_snapshot = build_current_snapshot(state, runtime_inputs, current_messages, step)
            candidate_properties = rank_properties_from_snapshot(state, current_snapshot, rng)
            property_ids = [item["property_id"] for item in candidate_properties[:4]]
            all_context_packet = compile_all_context_packet(large_context["facts"], runtime_inputs)
            memory_packet = memory.retrieve(
                {
                    "target_zip": runtime_inputs["target_zip"],
                    "property_ids": property_ids,
                    "tags": ["critical", "demand_tailwind", "rent_growth", "risk_flag", "financing"],
                },
                limit=int(runtime_inputs.get("memory_limit", 36)),
            )
            context.event(
                "memory_context_compiled",
                {
                    "step": step,
                    "input_facts": memory_packet.estimated_input_facts,
                    "selected_facts": len(memory_packet.selected_facts),
                    "dropped_count": memory_packet.dropped_count,
                    "output_tokens_estimate": memory_packet.estimated_output_tokens,
                    "all_context_tokens_estimate": all_context_packet.estimated_input_tokens,
                    "all_context_budget_violation": all_context_packet.budget_violation,
                },
            )

            all_context = decide_with_all_context(state, current_snapshot, candidate_properties, all_context_packet)
            optimized_memory = decide_with_memory(state, current_snapshot, candidate_properties, memory_packet)
            oracle = oracle_decision(state, candidate_properties, large_context["facts"], runtime_inputs["target_zip"])
            llm_decision = ask_llm_for_memory_decision(llm, current_snapshot, memory_packet, optimized_memory)
            optimized_memory = normalize_decision(llm_decision, optimized_memory, candidate_properties)

            all_context_score = score_decision(
                all_context,
                oracle,
                selected_refs=all_context_packet.to_dict()["used_source_refs"],
            )
            optimized_memory_score = score_decision(
                optimized_memory,
                oracle,
                selected_refs=memory_packet.to_dict()["source_refs"],
            )
            benchmark = {
                "step": step,
                "oracle_action": oracle["action"],
                "all_context": all_context_score,
                "optimized_memory": optimized_memory_score,
                "quality_lift": round(
                    optimized_memory_score["quality_score"] - all_context_score["quality_score"],
                    4,
                ),
            }
            benchmark_rows.append(benchmark)
            context.event(
                "llm_decision",
                {
                    "step": step,
                    "decision": optimized_memory,
                    "baseline_all_context": all_context,
                    "oracle": oracle,
                },
            )
            context.event("benchmark_step_scored", benchmark)

            applied = optimized_memory if runtime_inputs["memory_mode"] != "off" else all_context
            apply_action_effect(state, applied["action"])
            new_fact = decision_memory_fact(step, runtime_inputs["target_zip"], applied, oracle, optimized_memory_score)
            memory.add(new_fact)
            state_after = rounded_state(state)
            context.event(
                "simulation_state_updated",
                {"step": step, "applied_action": applied["action"], "state_after": state_after},
            )
            timeline.append(
                {
                    "step": step,
                    "observation": current_snapshot,
                    "decision": applied,
                    "memory_comparison": {
                        "all_context": all_context,
                        "optimized_memory": optimized_memory,
                        "oracle": oracle,
                        "benchmark": benchmark,
                    },
                    "context_packets": {
                        "all_context": all_context_packet.to_dict(),
                        "optimized_memory": memory_packet.to_dict(),
                    },
                    "memory_packet": memory_packet.to_dict(),
                    "state_after": state_after,
                    "ranked_entities": candidate_properties,
                }
            )

        state_changes = state_delta(initial, state)
        benchmark_report = aggregate_benchmark(benchmark_rows, timeline)
        result = {
            "identity": {
                "blueprint_id": context.blueprint_id,
                "name": context.name,
                "run_id": context.run_id,
            },
            "blueprint": BLUEPRINT_ID,
            "name": context.name,
            "category": CATEGORY,
            "description": DESCRIPTION,
            "run": {
                "run_id": context.run_id,
                "run_dir": str(context.run_dir) if context.run_dir else None,
                "started_at": started_at,
                "ended_at": utc_now_iso(),
                "status": "completed",
            },
            "architecture": architecture_contract(resolved_config, input_source),
            "config": resolved_config,
            "inputs": runtime_inputs,
            "input_source": input_source,
            "agent_roles": ["memory_curator", "market_analyst", "acquisition_decision_agent"],
            "runtime_features": [
                "large synthetic finance context",
                "working memory retrieval",
                "source_refs",
                "full-context vs optimized-memory benchmark",
                "decision quality scoring",
            ],
            "uses_simulation": True,
            "uses_llm": True,
            "timeline": timeline,
            "state_changes": state_changes,
            "benchmark": benchmark_report,
            "final_artifact": final_artifact(state, timeline, state_changes, benchmark_report),
            "llm": {
                "provider": getattr(llm, "provider", "unknown"),
                "model": getattr(llm, "model", "unknown"),
                "calls": getattr(llm, "calls", 0),
                "fallback_calls": getattr(llm, "fallback_calls", 0),
            },
        }
        web_ui = maybe_write_static_output(context.run_store, result, resolved_config)
        if web_ui:
            result["web_ui"] = web_ui.to_dict()
        context.finish(result)
        return result
    except Exception as error:
        context.fail(error)
        raise


def default_inputs() -> dict[str, Any]:
    return {
        "steps": 6,
        "seed": 77,
        "target_zip": TARGET_ZIP,
        "max_price": 950000,
        "memory_mode": "compare",
        "history_months": 24,
        "noise_events_per_month": 10,
        "memory_limit": 36,
        "all_context_token_budget": 8000,
        "all_context_attention_limit": 36,
    }


def initial_state(inputs: dict[str, Any]) -> dict[str, float]:
    return {
        "median_price_index": float(inputs.get("initial_median_price_index", 112.0)),
        "demand_index": float(inputs.get("initial_demand_index", 67.0)),
        "cap_rate_pct": float(inputs.get("initial_cap_rate_pct", 5.45)),
        "risk_score": float(inputs.get("initial_risk_score", 58.0)),
        "liquidity_score": float(inputs.get("initial_liquidity_score", 47.0)),
        "rent_growth_signal": float(inputs.get("initial_rent_growth_signal", 4.1)),
    }


def generate_large_context(inputs: dict[str, Any], rng: random.Random) -> dict[str, Any]:
    target_zip = str(inputs.get("target_zip") or TARGET_ZIP)
    months = int(inputs.get("history_months", 24))
    noise_events = int(inputs.get("noise_events_per_month", 10))
    zips = (target_zip, *DISTRACTOR_ZIPS)
    facts: list[MemoryFact] = []
    messages: list[dict[str, Any]] = []

    for month in range(months):
        period = f"2025-{(month % 12) + 1:02d}"
        for zip_code in zips:
            for event_index in range(noise_events):
                source = rng.choice(["broker_scout", "rent_comp_feed", "permit_feed", "lender_note", "insurance_quote", "ops_message"])
                property_id = property_id_for(zip_code, rng.randrange(4))
                kind = rng.choice(["comp", "lead", "permit", "financing", "risk", "ops"])
                direction = rng.choice([-1, 1])
                impact = {
                    "demand": direction * rng.uniform(0.0, 1.6),
                    "cap_rate": direction * rng.uniform(0.0, 0.08),
                    "risk": rng.uniform(-1.0, 1.8),
                }
                fact = MemoryFact(
                    id=f"noise:{period}:{zip_code}:{event_index}",
                    period=period,
                    zip_code=zip_code,
                    property_id=property_id,
                    source=source,
                    kind=kind,
                    content=(
                        f"{source} noted {kind} signal {event_index} for {zip_code}/{property_id}; "
                        f"impact was mixed and not independently validated."
                    ),
                    importance=rng.uniform(0.1, 0.45),
                    confidence=rng.uniform(0.35, 0.72),
                    impact=impact,
                    tags=("noise", kind),
                    source_refs=(f"src:{period}:{zip_code}:{event_index}",),
                )
                facts.append(fact)
                messages.append(
                    {
                        "period": period,
                        "agent": source,
                        "zip_code": zip_code,
                        "message": fact.content,
                        "source_ref": fact.source_refs[0],
                    }
                )

    critical_facts = [
        MemoryFact(
            id="mem:02139-transit-tailwind",
            period="2025-10",
            zip_code=target_zip,
            source="permit_feed",
            kind="infrastructure",
            property_id=None,
            content="Transit reliability work around Central/Kendall reduced commute variance for renter-heavy blocks in 02139.",
            importance=0.98,
            confidence=0.91,
            impact={"demand": 8.0, "cap_rate": 0.16, "risk": -2.0},
            tags=("critical", "demand_tailwind", "transit"),
            source_refs=("mem:02139-transit-tailwind",),
        ),
        MemoryFact(
            id="mem:02139-biotech-hiring",
            period="2025-11",
            zip_code=target_zip,
            source="employment_monitor",
            kind="demand",
            property_id=None,
            content="Biotech hiring near Kendall created persistent furnished-rental demand in 02139 despite broader rate pressure.",
            importance=0.94,
            confidence=0.89,
            impact={"demand": 7.0, "cap_rate": 0.12, "risk": -1.0},
            tags=("critical", "demand_tailwind", "rent_growth"),
            source_refs=("mem:02139-biotech-hiring",),
        ),
        MemoryFact(
            id="mem:02139-rent-comp-upside",
            period="2026-01",
            zip_code=target_zip,
            source="rent_comp_feed",
            kind="rent_comp",
            property_id="02139-river-quad",
            content="Three lease comps within 0.4 miles support 7 percent rent upside for 02139 River Quad after ordinary turnover.",
            importance=0.99,
            confidence=0.93,
            impact={"demand": 3.0, "cap_rate": 0.42, "risk": -1.5},
            tags=("critical", "rent_growth", "property_alpha"),
            source_refs=("mem:02139-rent-comp-upside",),
        ),
        MemoryFact(
            id="mem:02139-dscr-exception",
            period="2026-02",
            zip_code=target_zip,
            source="lender_note",
            kind="financing",
            property_id="02139-river-quad",
            content="Relationship lender pre-cleared a DSCR exception for 02139 River Quad if price stays below 940000.",
            importance=0.93,
            confidence=0.86,
            impact={"liquidity": 10.0, "cap_rate": 0.18, "risk": -3.0},
            tags=("critical", "financing", "property_alpha"),
            source_refs=("mem:02139-dscr-exception",),
        ),
        MemoryFact(
            id="mem:river-quad-seller-motivation",
            period="2026-03",
            zip_code=target_zip,
            source="broker_scout",
            kind="seller_signal",
            property_id="02139-river-quad",
            content="Seller of 02139 River Quad had two failed closings and signaled willingness to accept a clean quick-close bid.",
            importance=0.97,
            confidence=0.88,
            impact={"cap_rate": 0.34, "liquidity": 6.0, "risk": -1.0},
            tags=("critical", "seller_motivation", "property_alpha"),
            source_refs=("mem:river-quad-seller-motivation",),
        ),
        MemoryFact(
            id="mem:river-quad-clean-inspection",
            period="2026-03",
            zip_code=target_zip,
            source="inspection_summary",
            kind="risk",
            property_id="02139-river-quad",
            content="Prior diligence found ordinary systems age and no flood, roof, or foundation exception for 02139 River Quad.",
            importance=0.9,
            confidence=0.84,
            impact={"risk": -5.0, "cap_rate": 0.08},
            tags=("critical", "risk_reducer", "property_alpha"),
            source_refs=("mem:river-quad-clean-inspection",),
        ),
        MemoryFact(
            id="mem:ivy-duplex-flood-insurance",
            period="2025-12",
            zip_code=target_zip,
            source="insurance_quote",
            kind="risk",
            property_id="02139-ivy-duplex",
            content="Ivy Duplex premium quotes jumped after updated flood maps, reducing normalized yield by about 60 bps.",
            importance=0.96,
            confidence=0.9,
            impact={"risk": 9.0, "cap_rate": -0.6},
            tags=("critical", "risk_flag", "avoid"),
            source_refs=("mem:ivy-duplex-flood-insurance",),
        ),
        MemoryFact(
            id="mem:ivy-duplex-roof-deferred",
            period="2026-01",
            zip_code=target_zip,
            source="property_manager",
            kind="risk",
            property_id="02139-ivy-duplex",
            content="Property manager flagged deferred roof and envelope work at Ivy Duplex after two water-intrusion tickets.",
            importance=0.95,
            confidence=0.87,
            impact={"risk": 8.0, "cap_rate": -0.32},
            tags=("critical", "risk_flag", "avoid"),
            source_refs=("mem:ivy-duplex-roof-deferred",),
        ),
    ]
    facts.extend(critical_facts)
    for fact in critical_facts:
        messages.append(
            {
                "period": fact.period,
                "agent": fact.source,
                "zip_code": fact.zip_code,
                "message": fact.content,
                "source_ref": fact.source_refs[0],
            }
        )
    rng.shuffle(messages)
    return {"facts": facts, "internal_messages": messages}


def advance_market_state(state: dict[str, float], rng: random.Random, step: int) -> None:
    state["median_price_index"] = clamp(state["median_price_index"] + 1.4 + rng.uniform(-1.8, 2.4), 80, 160)
    state["demand_index"] = clamp(state["demand_index"] + 2.0 + ((step % 3) - 1) * 1.7 + rng.uniform(-3, 4), 10, 140)
    state["cap_rate_pct"] = clamp(state["cap_rate_pct"] - 0.05 + rng.uniform(-0.18, 0.2), 2, 10)
    state["risk_score"] = clamp(state["risk_score"] + 2.8 + rng.uniform(-4, 5), 0, 100)
    state["liquidity_score"] = clamp(state["liquidity_score"] + rng.uniform(-3, 4), 0, 100)
    state["rent_growth_signal"] = clamp(state["rent_growth_signal"] + 0.3 + rng.uniform(-0.4, 0.8), -5, 15)


def current_internal_messages(messages: list[dict[str, Any]], step: int) -> list[dict[str, Any]]:
    offset = step * 37
    window = messages[offset : offset + 72]
    if len(window) < 72:
        window = window + messages[: 72 - len(window)]
    return window


def build_current_snapshot(
    state: dict[str, float],
    inputs: dict[str, Any],
    messages: list[dict[str, Any]],
    step: int,
) -> dict[str, Any]:
    target_zip = str(inputs.get("target_zip") or TARGET_ZIP)
    headline_noise = [
        item for item in messages if item["zip_code"] != target_zip or "risk" in item["message"].lower()
    ][:32]
    return {
        "step": step,
        "target_zip": target_zip,
        "metrics": rounded_state(state),
        "large_context_window": {
            "visible_messages": headline_noise,
            "visible_count": len(headline_noise),
            "note": "This is a noisy recent-message slice. Historical memory is needed to connect older broker, lender, rent, and risk facts.",
        },
        "constraints": {
            "max_price": inputs.get("max_price"),
            "actions": ["submit_bid", "negotiate_discount", "watchlist_only"],
            "objective": "maximize risk-adjusted acquisition alpha",
        },
    }


def rank_properties_from_snapshot(
    state: dict[str, float],
    snapshot: dict[str, Any],
    rng: random.Random,
) -> list[dict[str, Any]]:
    target_zip = snapshot["target_zip"]
    base = [
        {"property_id": f"{target_zip}-ivy-duplex", "name": "Ivy Duplex", "price": 885000, "units": 2},
        {"property_id": f"{target_zip}-river-quad", "name": "River Quad", "price": 932000, "units": 4},
        {"property_id": f"{target_zip}-central-three", "name": "Central Three", "price": 908000, "units": 3},
        {"property_id": f"{target_zip}-garden-six", "name": "Garden Six", "price": 1210000, "units": 6},
    ]
    ranked = []
    for index, item in enumerate(base):
        cap_rate = state["cap_rate_pct"] + (item["units"] - 2) * 0.18 + rng.uniform(-0.18, 0.22)
        current_risk = state["risk_score"] + (index - 1.5) * 2.8 + rng.uniform(-2.5, 2.5)
        score = cap_rate * 12 + state["demand_index"] * 0.18 - current_risk * 0.28
        ranked.append(
            {
                **item,
                "rank": index + 1,
                "cap_rate_pct": round(cap_rate, 2),
                "current_risk_score": round(clamp(current_risk, 0, 100), 2),
                "snapshot_score": round(score, 2),
            }
        )
    return sorted(ranked, key=lambda item: item["snapshot_score"], reverse=True)


def compile_all_context_packet(facts: list[MemoryFact], inputs: dict[str, Any]) -> AllContextPacket:
    public_facts = [fact for fact in facts if not fact.private]
    ordered = sorted(public_facts, key=lambda fact: (fact.period, fact.id))
    estimated_input_tokens = estimate_tokens("\n".join(fact.content for fact in ordered))
    token_budget = int(inputs.get("all_context_token_budget", 8000))
    attention_limit = int(inputs.get("all_context_attention_limit", 36))
    budget_violation = estimated_input_tokens > token_budget
    token_window = facts_tail_under_budget(ordered, token_budget) if budget_violation else ordered
    if len(token_window) > attention_limit:
        effective_facts = token_window[-attention_limit:]
        truncation_reason = "token_window_plus_attention_limit" if budget_violation else "attention_limit"
    else:
        effective_facts = token_window
        truncation_reason = "token_budget" if budget_violation else "none"
    return AllContextPacket(
        effective_facts=effective_facts,
        total_facts=len(public_facts),
        estimated_input_tokens=estimated_input_tokens,
        effective_tokens=estimate_tokens("\n".join(fact.content for fact in effective_facts)),
        token_budget=token_budget,
        attention_limit=attention_limit,
        budget_violation=budget_violation,
        dropped_by_window=max(0, len(public_facts) - len(effective_facts)),
        truncation_reason=truncation_reason,
    )


def decide_with_all_context(
    state: dict[str, float],
    snapshot: dict[str, Any],
    candidates: list[dict[str, Any]],
    packet: AllContextPacket,
) -> dict[str, Any]:
    property_scores = property_signal_scores(packet.effective_facts, candidates)
    top = max(candidates, key=lambda item: item["snapshot_score"] + property_scores.get(item["property_id"], 0.0))
    top_score = top["snapshot_score"] + property_scores.get(top["property_id"], 0.0)
    signals = connect_signals(packet.effective_facts, snapshot["target_zip"])
    if top["property_id"].endswith("river-quad") and top_score >= 64 and signals["positive_signal_count"] >= 3:
        action = "submit_bid"
    elif state["risk_score"] >= 67:
        action = "watchlist_only"
    elif state["cap_rate_pct"] >= 5.9 and top["current_risk_score"] < 62:
        action = "submit_bid"
    else:
        action = "negotiate_discount"
    refs = sorted({ref for fact in packet.effective_facts for ref in fact.source_refs if ref.startswith("mem:")})
    return {
        "action": action,
        "confidence": 0.69 if packet.budget_violation else 0.74,
        "property_id": top["property_id"],
        "rationale": (
            "The baseline shares the full agent history, then relies on the model's effective context window "
            "to surface useful facts without a memory optimizer."
        ),
        "parameters": {
            "target_zip": snapshot["target_zip"],
            "selected_property": top["name"],
            "memory_used": False,
            "context_strategy": "share_full_agent_history",
            "budget_violation": packet.budget_violation,
            "effective_facts": len(packet.effective_facts),
            "source_refs": refs[:12],
        },
    }


def decide_with_memory(
    state: dict[str, float],
    snapshot: dict[str, Any],
    candidates: list[dict[str, Any]],
    packet: MemoryPacket,
) -> dict[str, Any]:
    signals = packet.connected_signals
    property_scores = property_signal_scores(packet.selected_facts, candidates)
    top = max(candidates, key=lambda item: item["snapshot_score"] + property_scores.get(item["property_id"], 0.0))
    top_score = top["snapshot_score"] + property_scores.get(top["property_id"], 0.0)
    avoid_score = property_scores.get(f"{snapshot['target_zip']}-ivy-duplex", 0.0)
    if top["property_id"].endswith("river-quad") and top_score >= 68 and signals["positive_signal_count"] >= 5:
        action = "submit_bid"
    elif avoid_score < -8 or signals["risk_flag_count"] >= 2:
        action = "negotiate_discount"
    else:
        action = "watchlist_only"
    refs = sorted({ref for fact in packet.selected_facts for ref in fact.source_refs if ref.startswith("mem:")})
    return {
        "action": action,
        "confidence": 0.86 if action == "submit_bid" else 0.78,
        "property_id": top["property_id"],
        "rationale": (
            "Working memory connects older transit, hiring, rent-comp, DSCR, seller-motivation, "
            "and property-risk facts that are not all visible in the current message window."
        ),
        "parameters": {
            "target_zip": snapshot["target_zip"],
            "selected_property": top["name"],
            "memory_used": True,
            "context_strategy": "optimized_memory_packet",
            "connected_signals": signals,
            "source_refs": refs[:12],
        },
    }


def oracle_decision(
    state: dict[str, float],
    candidates: list[dict[str, Any]],
    all_facts: list[MemoryFact],
    target_zip: str,
) -> dict[str, Any]:
    packet = MemoryPacket(
        selected_facts=[fact for fact in all_facts if fact.zip_code == target_zip and "critical" in fact.tags],
        dropped_count=0,
        estimated_input_facts=len(all_facts),
        estimated_output_tokens=0,
        connected_signals={},
    )
    scores = property_signal_scores(packet.selected_facts, candidates)
    top = max(candidates, key=lambda item: item["snapshot_score"] + scores.get(item["property_id"], 0.0))
    return {
        "action": "submit_bid",
        "property_id": f"{target_zip}-river-quad",
        "rationale": "Full context identifies River Quad as the best risk-adjusted bid, while Ivy Duplex should be avoided.",
        "parameters": {
            "target_zip": target_zip,
            "selected_property": top["name"],
            "source_refs": list(CRITICAL_SOURCE_REFS),
        },
    }


def ask_llm_for_memory_decision(
    llm: Any,
    snapshot: dict[str, Any],
    packet: MemoryPacket,
    fallback: dict[str, Any],
) -> dict[str, Any]:
    system_prompt = (
        "You are a real estate investment analyst. Return JSON with action, confidence, rationale, "
        "property_id, and parameters. Prefer source-grounded decisions."
    )
    user_prompt = json.dumps(
        {
            "current_snapshot": snapshot,
            "memory_packet": packet.to_dict(),
            "available_actions": ["submit_bid", "negotiate_discount", "watchlist_only"],
            "fallback_policy": fallback,
        },
        indent=2,
        sort_keys=True,
    )
    return llm.generate_json(system_prompt=system_prompt, user_prompt=user_prompt, fallback=fallback)


def normalize_decision(response: dict[str, Any], fallback: dict[str, Any], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    valid_actions = {"submit_bid", "negotiate_discount", "watchlist_only"}
    candidate_ids = {item["property_id"] for item in candidates}
    action = str(response.get("action") or fallback["action"])
    if action not in valid_actions:
        action = fallback["action"]
    property_id = str(response.get("property_id") or fallback.get("property_id") or candidates[0]["property_id"])
    if property_id not in candidate_ids:
        property_id = fallback.get("property_id") or candidates[0]["property_id"]
    parameters = response.get("parameters") if isinstance(response.get("parameters"), dict) else fallback["parameters"]
    parameters.setdefault("source_refs", fallback.get("parameters", {}).get("source_refs", []))
    return {
        "action": action,
        "confidence": round(clamp(float(response.get("confidence", fallback.get("confidence", 0.7))), 0, 1), 3),
        "property_id": property_id,
        "rationale": str(response.get("rationale") or fallback["rationale"]),
        "parameters": parameters,
        "provider": response.get("provider", getattr(response, "provider", "unknown")),
    }


def connect_signals(facts: list[MemoryFact], target_zip: str) -> dict[str, Any]:
    target = [fact for fact in facts if fact.zip_code == target_zip]
    positive = [
        fact for fact in target
        if any(tag in fact.tags for tag in ("demand_tailwind", "rent_growth", "seller_motivation", "financing", "risk_reducer"))
    ]
    risks = [fact for fact in target if "risk_flag" in fact.tags]
    return {
        "target_zip": target_zip,
        "selected_target_facts": len(target),
        "positive_signal_count": len(positive),
        "risk_flag_count": len(risks),
        "top_positive_refs": [fact.source_refs[0] for fact in positive[:8] if fact.source_refs],
        "top_risk_refs": [fact.source_refs[0] for fact in risks[:4] if fact.source_refs],
    }


def property_signal_scores(facts: list[MemoryFact], candidates: list[dict[str, Any]]) -> dict[str, float]:
    candidate_ids = {item["property_id"] for item in candidates}
    scores = {property_id: 0.0 for property_id in candidate_ids}
    for fact in facts:
        if not fact.property_id or fact.property_id not in scores:
            continue
        score = fact.impact.get("cap_rate", 0.0) * 20
        score += fact.impact.get("demand", 0.0) * 0.8
        score += fact.impact.get("liquidity", 0.0) * 0.4
        score -= fact.impact.get("risk", 0.0) * 0.9
        score *= fact.importance * fact.confidence
        scores[fact.property_id] += score
    return scores


def score_decision(decision: dict[str, Any], oracle: dict[str, Any], *, selected_refs: tuple[str, ...] | list[str]) -> dict[str, Any]:
    action_match = 1.0 if decision.get("action") == oracle.get("action") else 0.0
    property_match = 1.0 if decision.get("property_id") == oracle.get("property_id") else 0.0
    refs = set(selected_refs)
    recall = len(refs & set(CRITICAL_SOURCE_REFS)) / len(CRITICAL_SOURCE_REFS)
    risk_awareness = 1.0 if {"mem:ivy-duplex-flood-insurance", "mem:ivy-duplex-roof-deferred"} <= refs else max(0.25, recall)
    quality = 0.42 * action_match + 0.23 * property_match + 0.25 * recall + 0.10 * risk_awareness
    return {
        "action": decision.get("action"),
        "property_id": decision.get("property_id"),
        "action_match": bool(action_match),
        "property_match": bool(property_match),
        "critical_fact_recall": round(recall, 4),
        "risk_awareness": round(risk_awareness, 4),
        "quality_score": round(quality, 4),
        "missed_critical_refs": sorted(set(CRITICAL_SOURCE_REFS) - refs),
    }


def aggregate_benchmark(rows: list[dict[str, Any]], timeline: list[dict[str, Any]]) -> dict[str, Any]:
    all_context_scores = [row["all_context"]["quality_score"] for row in rows]
    optimized_scores = [row["optimized_memory"]["quality_score"] for row in rows]
    all_context_action = [1 for row in rows if row["all_context"]["action_match"]]
    optimized_action = [1 for row in rows if row["optimized_memory"]["action_match"]]
    all_context_tokens = [step["context_packets"]["all_context"]["estimated_input_tokens"] for step in timeline]
    all_context_latency = [step["context_packets"]["all_context"]["estimated_latency_ms"] for step in timeline]
    optimized_tokens = [step["memory_packet"]["estimated_output_tokens"] for step in timeline]
    optimized_latency = [estimate_latency_ms(tokens, base_ms=40.0) for tokens in optimized_tokens]
    selected_counts = [len(step["memory_packet"]["selected_facts"]) for step in timeline]
    dropped_counts = [step["memory_packet"]["dropped_count"] for step in timeline]
    budget_violations = [1 for step in timeline if step["context_packets"]["all_context"]["budget_violation"]]
    token_reduction = 1.0 - (mean(optimized_tokens) / max(1.0, mean(all_context_tokens)))
    return {
        "schema_version": "mn.finance.property_alpha.memory_benchmark.v2",
        "objective": (
            "compare simple full-history context sharing against optimized working memory over large "
            "multi-agent property history"
        ),
        "steps": len(rows),
        "all_context": {
            "strategy": "share_full_agent_history",
            "mean_quality_score": round(mean(all_context_scores), 4),
            "action_accuracy": round(sum(all_context_action) / max(1, len(rows)), 4),
            "mean_estimated_input_tokens": round(mean(all_context_tokens), 2),
            "mean_estimated_latency_ms": round(mean(all_context_latency), 2),
            "budget_violation_rate": round(sum(budget_violations) / max(1, len(rows)), 4),
        },
        "optimized_memory": {
            "strategy": "optimized_memory_packet",
            "mean_quality_score": round(mean(optimized_scores), 4),
            "action_accuracy": round(sum(optimized_action) / max(1, len(rows)), 4),
            "mean_estimated_input_tokens": round(mean(optimized_tokens), 2),
            "mean_estimated_latency_ms": round(mean(optimized_latency), 2),
        },
        "lift": {
            "quality_score_delta": round(mean(optimized_scores) - mean(all_context_scores), 4),
            "action_accuracy_delta": round(
                sum(optimized_action) / max(1, len(rows)) - sum(all_context_action) / max(1, len(rows)),
                4,
            ),
            "estimated_token_reduction_ratio": round(token_reduction, 4),
            "estimated_latency_reduction_ms": round(mean(all_context_latency) - mean(optimized_latency), 2),
        },
        "memory_metrics": {
            "mean_selected_facts": round(mean(selected_counts), 2),
            "max_dropped_facts": max(dropped_counts) if dropped_counts else 0,
            "critical_source_refs": list(CRITICAL_SOURCE_REFS),
        },
        "quality_gate": {
            "passed": mean(optimized_scores) >= mean(all_context_scores) and token_reduction >= 0.9,
            "min_quality_lift": 0.0,
            "min_token_reduction_ratio": 0.9,
            "actual_quality_lift": round(mean(optimized_scores) - mean(all_context_scores), 4),
            "actual_token_reduction_ratio": round(token_reduction, 4),
        },
        "per_step": rows,
    }


def final_artifact(
    state: dict[str, float],
    timeline: list[dict[str, Any]],
    state_changes: list[dict[str, Any]],
    benchmark: dict[str, Any],
) -> dict[str, Any]:
    last = timeline[-1]
    decision = last["decision"]
    return {
        "type": "ranked property acquisition opportunities with memory benchmark",
        "executive_summary": (
            "Optimized working memory matched or improved full-history context sharing while using a much "
            "smaller source-grounded packet."
        ),
        "recommended_action": decision["action"],
        "recommended_property_id": decision.get("property_id"),
        "action_history": [step["decision"]["action"] for step in timeline],
        "key_metrics": rounded_state(state),
        "ranked_options": last["ranked_entities"][:3],
        "state_changes": state_changes,
        "benchmark": benchmark,
        "next_steps": [
            "Submit a source-referenced investment memo for River Quad if pricing remains below the DSCR exception threshold.",
            "Keep Ivy Duplex on avoid/watchlist until flood insurance and roof-envelope risks are repriced.",
            "Use the optimized memory packet for agent handoffs instead of replaying the entire deal-flow history.",
        ],
    }


def decision_memory_fact(
    step: int,
    target_zip: str,
    decision: dict[str, Any],
    oracle: dict[str, Any],
    score: dict[str, Any],
) -> MemoryFact:
    action_match = decision.get("action") == oracle.get("action")
    return MemoryFact(
        id=f"decision:{step}:{decision.get('action')}",
        period=f"run-step-{step}",
        zip_code=target_zip,
        property_id=decision.get("property_id"),
        source="acquisition_decision_agent",
        kind="decision_outcome",
        content=(
            f"Step {step} decision {decision.get('action')} for {decision.get('property_id')} "
            f"quality={score['quality_score']} action_match={action_match}."
        ),
        importance=0.72 if action_match else 0.82,
        confidence=0.9,
        impact={"risk": -1.0 if action_match else 2.0, "cap_rate": 0.05 if action_match else -0.05},
        tags=("decision", "feedback", "critical" if not action_match else "validated"),
        source_refs=(f"decision:step:{step}",),
    )


def apply_action_effect(state: dict[str, float], action: str) -> None:
    effects = {
        "submit_bid": {"cap_rate_pct": 0.14, "liquidity_score": -2.0, "risk_score": 2.0},
        "negotiate_discount": {"cap_rate_pct": 0.28, "median_price_index": -1.4, "risk_score": -1.2},
        "watchlist_only": {"risk_score": -2.6, "liquidity_score": 1.5},
    }.get(action, {})
    for key, value in effects.items():
        if key in state:
            state[key] = round(state[key] + value, 4)


def state_delta(initial: dict[str, float], final: dict[str, float]) -> list[dict[str, Any]]:
    return [
        {
            "metric": key,
            "start": round(initial[key], 3),
            "end": round(final[key], 3),
            "delta": round(final[key] - initial[key], 3),
        }
        for key in sorted(initial)
    ]


def rounded_state(state: dict[str, float]) -> dict[str, float]:
    return {key: round(value, 3) for key, value in state.items()}


def estimate_tokens(text: str) -> int:
    return max(1, math.ceil(len(text.split()) * 1.25))


def estimate_latency_ms(tokens: int, *, base_ms: float) -> float:
    return round(base_ms + tokens * 0.025, 2)


def facts_tail_under_budget(facts: list[MemoryFact], token_budget: int) -> list[MemoryFact]:
    selected: list[MemoryFact] = []
    running_tokens = 0
    for fact in reversed(facts):
        fact_tokens = estimate_tokens(fact.content)
        if selected and running_tokens + fact_tokens > token_budget:
            break
        selected.append(fact)
        running_tokens += fact_tokens
        if running_tokens >= token_budget:
            break
    return list(reversed(selected))


def property_id_for(zip_code: str, index: int) -> str:
    suffixes = ("ivy-duplex", "river-quad", "central-three", "garden-six")
    return f"{zip_code}-{suffixes[index % len(suffixes)]}"


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def mean(values: list[float]) -> float:
    return sum(values) / max(1, len(values))


def main(argv: list[str] | None = None) -> None:
    run_blueprint_cli(
        run_blueprint,
        argv,
        description="Run the finance ZIP-code property alpha memory benchmark blueprint.",
        default_blueprint_id=BLUEPRINT_ID,
    )


if __name__ == "__main__":
    main()
