"""Case-scoped evidence operations over SDK retrieval and shared conversion."""


def descriptor():
    def arguments(properties, required):
        return {"type": "object", "properties": properties,
                "required": required, "additionalProperties": False}

    return {
        "id": "otterdesk.litigation.evidence",
        "module": "domain.app",
        "description": "Search authorized original sources, revisit verified citations, and inspect frozen PDF pages.",
        "operations": {
            "search": {"arguments": arguments({
                "query": {"type": "string", "minLength": 1, "maxLength": 4000},
                "top_k": {"type": "integer", "minimum": 1, "maximum": 20},
            }, ["query"])},
            "passage": {"arguments": arguments({
                "evidence_id": {"type": "string", "minLength": 1, "maxLength": 128},
            }, ["evidence_id"])},
            "extract_pages": {"arguments": arguments({
                "source_id": {"type": "string", "minLength": 1, "maxLength": 4000},
            }, ["source_id"])},
            "temporal_paths": {"arguments": arguments({
                "seeds": {"type": "array", "minItems": 1, "maxItems": 16,
                          "items": {"type": "string", "minLength": 1, "maxLength": 4000}},
                "target": {"type": "string", "minLength": 1, "maxLength": 4000},
            }, ["seeds"])},
            "compare_event_order": {"arguments": arguments({
                "earlier_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "later_id": {"type": "string", "minLength": 1, "maxLength": 128},
            }, ["earlier_id", "later_id"])},
            "chronology": {"arguments": arguments({}, [])},
        },
    }
