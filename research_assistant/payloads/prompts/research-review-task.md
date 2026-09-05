# Research Assistant Specialist Review Task

## Goal

Review the supplied candidate packet from the assigned specialist role without rewriting the packet.

## Instructions

- Use only the supplied evidence posture, candidate summaries, and source refs.
- Return exactly the compact specialist-review shape: `actor_id`, `role`, `summary`, `findings`, `risks`, `recommended_next_step`, and numeric `confidence`.
- Keep `summary` under 60 words, use at most three one-sentence findings and three one-sentence risks, and keep the entire JSON object under 500 tokens.
- Flag missing traceability, falsifiability, controls, uncertainty, or review boundaries; do not restate full hypotheses or experiment procedures.

## Restrictions

- Do not invent sources, results, novelty, causality, efficacy, safety, or approvals.
- Do not request tools or perform new research in this review.
- Do not execute experiments, modify live systems, contact participants, publish a manuscript, or make a clinical or safety decision.
