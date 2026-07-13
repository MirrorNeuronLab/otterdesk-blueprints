# AI Co-Scientist Workflow Inspiration

Google Research describes AI co-scientist as a multi-agent system that uses specialized Generation, Reflection, Ranking, Evolution, Proximity, and Meta-review roles to iteratively generate and refine research hypotheses. It also describes a supervisor that translates a scientist's natural-language goal into a research-plan configuration and assigns work to specialized agents.

Source: Google Research, [Accelerating scientific breakthroughs with an AI co-scientist](https://research.google/blog/accelerating-scientific-breakthroughs-with-an-ai-co-scientist/), February 19, 2025.

This blueprint is inspired by the workflow pattern, not an implementation of Google's system. It uses a bounded set of role responsibilities appropriate for a portable local blueprint:

- **Generation** maps to topic framing and hypothesis generation.
- **Reflection** maps to skeptical, adversarial critique.
- **Ranking** maps to evidence-strength and review-posture ranking.
- **Evolution** maps to a bounded revision of a candidate after a specific critique.
- **Proximity** maps to overlap and novelty review with deliberately limited claims.
- **Meta-review** maps to a final audit of evidence, uncertainty, and blocked actions.

The additional experiment-design, code-planning, benchmark-planning, result-analysis, and drafting roles keep a research packet connected to the work required to test a hypothesis. No role validates a result, performs an experiment, or replaces human scientific review.
