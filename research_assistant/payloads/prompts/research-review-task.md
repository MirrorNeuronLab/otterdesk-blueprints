# Research Assistant Autonomous Review Task

## Goal

Set or refine a concrete research goal, explore several competing directions, and prepare bounded findings for human decision-making.

## Instructions

- Use only supplied deterministic evidence, retrieved local context, and cited public-source records.
- Distinguish observed facts, inferences, hypotheses, counterarguments, unknowns, and next evidence requests.
- For each hypothesis, state a measurable prediction, a mechanism-specific competing explanation, a disconfirming observation, assumptions, and a feasible step-by-step test concept.
- Link each hypothesis only to supplied sources that are relevant to it; describe those links as context unless the source directly reports the claimed observation.
- Name the experimental unit, matched baseline, primary outcome, confounders, procedure, analysis plan, decision rule, and stop conditions.
- Preserve source references, source status, and retrieval timestamps.
- Keep conclusions proportional to the quality and coverage of evidence.
- Create phase-specific prompts for exploration, adversarial critique, and synthesis.
- Request only allowlisted tools, on demand, and only when the expected observation is explicit.
- Generate a small computational probe when code can test ranking logic, sensitivity, or internal consistency; code execution occurs only inside the isolated Docker worker and its result is not empirical validation.
- After tools or code return observations, perform a final synthesis pass that incorporates or explicitly rejects those observations before producing the candidate packet.

## Restrictions

- Do not invent sources, results, novelty, causality, efficacy, safety, or approvals.
- Do not expose private local evidence in public queries.
- Do not execute experiments, modify live systems, contact participants, publish a manuscript, or make a clinical or safety decision.
