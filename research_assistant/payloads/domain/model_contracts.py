"""Research phase output contracts, shared by generation and validation."""

from .common import RESEARCH_ACTIONS


def _text():
    return {"type": "string", "minLength": 1, "maxLength": 1200}


def _array(items=None, *, minimum=0, maximum=3):
    return {"type": "array", "items": items or _text(), "minItems": minimum, "maxItems": maximum}


def _object(**properties):
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


def _choice(values):
    return {"type": "string", "enum": sorted(values)}


def phase_schema(phase, context):
    refs = context.get("source_refs") or []
    source_ref = _choice(refs) if refs else _text()
    support = _array(source_ref, minimum=int(bool(refs)), maximum=6)
    hypothesis = _object(
        statement=_text(), prediction=_text(), counterargument=_text(),
        disconfirming_observation=_text(), assumptions=_array(),
        evidence_support=support, evidence_status=_text(),
    )
    decision = dict(
        recommended_action=_choice(RESEARCH_ACTIONS),
        confidence=_choice(["low", "medium", "high"]), rationale=_text(),
    )
    if phase == "source_analysis":
        return _object(
            source_assessments=_array(_object(
                source_ref=source_ref, source_type=_text(),
                relevant_observations=_array(maximum=2), limitations=_array(maximum=2),
                use_in_synthesis=_text(),
            ), minimum=int(bool(refs)), maximum=len(refs)),
            cross_source_agreements=_array(), cross_source_tensions=_array(), evidence_gaps=_array(),
        )
    if phase == "question_decomposition":
        return _object(
            subquestions=_array(_object(
                subquestion_id=_text(), question=_text(), decision_relevance=_text(), evidence_needed=_array(),
            ), minimum=1, maximum=4),
            key_definitions=_array(), assumptions_to_test=_array(), stop_conditions=_array(),
        )
    if phase in {"competing_hypothesis_generation", "evidence_and_probe_revision"}:
        return _object(candidate_hypotheses=_array(hypothesis, minimum=1), **decision)
    if phase.startswith("adversarial_review_"):
        return _object(
            hypothesis_id={"const": context["hypothesis"]["hypothesis_id"], "type": "string"},
            strongest_counterargument=_text(), alternative_explanations=_array(maximum=2),
            confounders=_array(maximum=2), measurement_risks=_array(maximum=2),
            boundary_conditions=_array(maximum=2), decisive_disconfirming_observations=_array(minimum=1, maximum=2),
            revision_recommendation=_text(),
        )
    if phase == "gap_and_probe_planning":
        requests = []
        for tool in context["available_tools"]:
            arguments = (_object(candidates=_array(_object(statement=_text(), evidence_support=support), minimum=1))
                         if tool == "hypothesis_rank" else _object(query=_text()))
            requests.append(_object(tool=_choice([tool]), arguments=arguments))
        return _object(
            tool_requests=_array({"anyOf": requests}, maximum=2),
            generated_python={"type": "string", "maxLength": 20000},
        )
    if phase.startswith("experiment_design_"):
        return _object(experiment=_object(
            hypothesis_id={"const": context["hypothesis"]["hypothesis_id"], "type": "string"},
            objective=_text(), unit_of_analysis=_text(), baseline=_text(), intervention=_text(),
            primary_outcome=_text(), measurements=_array(minimum=1, maximum=5),
            procedure=_array(minimum=4, maximum=5), decision_rule=_text(), analysis_plan=_text(),
            stop_conditions=_array(minimum=1),
        ))
    if phase == "meta_review_and_ranking":
        ids = [item["hypothesis_id"] for item in context["candidate_hypotheses"]]
        return _object(
            ranking=_array(_object(
                hypothesis_id=_choice(ids), rank={"type": "integer", "minimum": 1, "maximum": len(ids)},
                priority_score={"type": "number", "minimum": 0, "maximum": 100}, rationale=_text(),
            ), minimum=len(ids), maximum=len(ids)),
            unresolved_gaps=_array(maximum=5), **decision,
        )
    if phase == "executive_synthesis":
        return _object(
            executive_summary=_text(), key_findings=_array(), decision_implications=_array(), caveats=_array(),
        )
    raise ValueError(f"Unknown research model phase: {phase}")


def validate_phase(phase, context, value):
    """Enforce identity coverage that a serving grammar cannot express."""
    if phase == "source_analysis":
        refs = [item["source_ref"] for item in value["source_assessments"]]
        if len(refs) != len(set(refs)):
            return None
    if phase == "meta_review_and_ranking":
        ranking = value["ranking"]
        ids = {item["hypothesis_id"] for item in context["candidate_hypotheses"]}
        if ({item["hypothesis_id"] for item in ranking} != ids
                or {item["rank"] for item in ranking} != set(range(1, len(ids) + 1))):
            return None
    return value


def review_schema(actor_id, role):
    return _object(
        actor_id={"type": "string", "const": actor_id}, role={"type": "string", "const": role},
        summary=_text(), findings=_array(), risks=_array(), recommended_next_step=_text(),
        confidence={"type": "number", "minimum": 0, "maximum": 1},
    )
