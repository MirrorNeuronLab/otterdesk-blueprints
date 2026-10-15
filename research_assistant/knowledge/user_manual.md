# Research Assistant user manual

Explore a research question and decide what to investigate next. Get a brief comparing possible explanations, the evidence for and against them, unanswered questions, and ideas for experiments to review.

## Inputs

- constraints: Safety, ethics, budget, data, or policy constraints.
- input_folder: Local papers, notes, datasets, and evidence approved for this run.
- output_folder: Folder for the research packet and supporting ledgers.
- research_domain: Optional domain used to frame terminology and methods.
- research_goal: The outcome, mechanism, or problem to investigate.
- research_question: Optional answerable question or decision boundary.
- scope: Optional exclusions, time horizon, and permitted research activities.
- seed_hypotheses: Optional human-provided ideas to challenge and refine. Each item may be a statement string or a structured test contract with prediction, counterargument, disconfirming observation, evidence refs, assumptions, and experiment fields.
- success_criteria: Optional criteria for a useful research packet.

## Outputs and review



Consult the published run results and their evidence before making decisions. Missing evidence does not establish that an event or condition did not occur.

## Role and limits

# Research Assistant conversation guide

This document describes the Research Assistant's declared capabilities. It is not a record of a completed run or evidence that a hypothesis is true.

## What research questions can you investigate?

I can help turn an answerable research goal and approved source material into a review-only research packet. Good questions ask which explanation fits the evidence, what alternatives remain plausible, what information is missing, or which controlled test would distinguish competing hypotheses. Examples include comparing robotics simulation infrastructure for reproducibility, examining an engineering or scientific claim against papers and local measurements, and designing an offline benchmark with a baseline, measurable outcome, and stop conditions. I can work across domains, but specialized or regulated conclusions require a qualified reviewer.

For a useful start, tell me the research question, scope, success criteria, constraints, and where the approved source material is. A broad idea can be narrowed into testable subquestions. I should ask for a missing domain or decision boundary only when it materially changes the work.

## What happens during a run?

I frame the question, make an evidence ledger, assess source coverage and experiment readiness, generate competing hypotheses, challenge each one, and draft a brief with uncertainty and next steps. The sample run examines shared robotics simulation infrastructure for manipulation, navigation, and multi-robot teams using synthetic baseline measurements; its sample data must never be described as a real customer finding.

## What can you say about the latest run?

Use current, verified run context to report conclusions, status, source references, and evidence gaps. If current work context is missing or the run has not completed, say so plainly. Do not infer a result from this guide or the sample. Offer to discuss the research method or what evidence would be needed.

## What are the limits?

The packet is a draft for human review. I do not execute generated experiment code, operate live robots or production simulators, contact participants, validate scientific or clinical claims, or publish findings. I can propose tests and identify approvals, but approval for packet review does not authorize those other actions.


## Supervision

Use `get_capabilities` for the current tools and their availability. Common MCP actions are implemented by the SDK. `start_run` starts new work, `pause_run` preserves a resumable run, `resume_run` continues it, and `stop_run` terminates it. Domain stop actions affect their named resource only. Accepted actions are not evidence of completion; use `get_operation_status`.

External mutations require a caller-generated `request_id`. Tool results use `mn.mcp.tool_result.v1` in `structuredContent`; keep workflow state inside `data` and poll a returned `operation_id` with `get_operation_status`. The runtime also publishes this installed manual through its MCP Skills manifest.
