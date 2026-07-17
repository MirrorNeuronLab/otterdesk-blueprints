# Drug Discovery Triage Playbook

Use this guidance as local retrieval context for review-only drug discovery triage.

## Evidence Grounding

- Separate disease rationale, target evidence, structure confidence, generated candidate properties, docking scores, toxicity filters, and literature notes.
- Treat generated structures and candidates as hypotheses until a domain scientist reviews the assumptions.
- Keep assay, wet-lab, animal, and clinical-readiness language out of automated recommendations unless source evidence explicitly supports it.

## Review Checks

- Confirm each target has a disease association source, biological plausibility note, and uncertainty statement.
- Confirm each candidate summary includes method, score direction, known limitations, and source references.
- Flag missing controls, unsupported affinity claims, safety gaps, and conflicts between evidence sources.

## Tool Boundaries

- Database lookups, structure generation, candidate generation, docking, and toxicity filters are tools for prioritization, not proof of efficacy.
- If a tool fails or returns thin evidence, preserve that status rather than filling the gap with generic biomedical language.
