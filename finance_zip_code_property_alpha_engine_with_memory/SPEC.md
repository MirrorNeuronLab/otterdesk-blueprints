# Zip Code Property Alpha Engine With Memory SPEC

## What We Want To Achieve

Build a reviewable financial decision-support workflow that helps Real-estate investors, acquisition analysts, property-tech teams, and diligence operators move from raw signals to an explainable recommendation. Rank property acquisition opportunities with working memory over large noisy deal-flow context. The target customer should understand what changed, why the system recommended an action, and what evidence a human should review before acting.

## Customer Problem

Property acquisition decisions often depend on older broker, lender, rent, insurance, and diligence facts that disappear inside large noisy deal flow. In a real customer environment, the pain is not only producing an answer; it is preserving context across changing inputs, exposing tradeoffs, and creating an audit trail that business, technical, or governance stakeholders can trust.

## Design Details

The blueprint is organized as a MirrorNeuron workflow with stable identity, configurable inputs, structured events, and a final artifact. The main agent role is Real estate investment analyst with working memory. The workflow uses zip-code property market simulation with large historical memory and demonstrates large synthetic finance context, working memory retrieval, source refs, decision quality benchmark, with/without memory comparison, and LLM investment reasoning.

The design is intentionally adapter-friendly. The prototype can run with bundled, mock, or synthetic data even when the current code has not implemented every production integration. The customer-facing contract stays centered on the same concepts: load inputs, observe current state, choose or score an action, emit traceable events, and write an artifact a reviewer can inspect.

A representative scenario is: A noisy current snapshot favors Ivy Duplex, but working memory recalls flood and roof risk while connecting River Quad rent upside, financing, and seller motivation.

## Input

The prototype accepts configuration for scenario identity, run controls, and domain inputs. Current adapters include `mock`, `json`, `file`, and `env_json`, so evaluators can start locally and later replace sample data with production data while preserving the same blueprint identity and output shape.

Important state inputs include `median_price_index`, `demand_index`, `cap_rate_pct`, `risk_score`, `liquidity_score`, and `rent_growth_signal`. Where the blueprint uses an action loop, the current action space includes `submit_bid`, `negotiate_discount`, and `watchlist_only`. For production use, the same contract should be fed by customer system-of-record data, business rules, approval policies, thresholds, and any regulated or safety-critical constraints needed for the operating environment.

## Output: Expected Customer Outcome

The expected customer outcome is ranked opportunities, source-grounded bid/watchlist recommendation, and memory decision-quality benchmark. A useful run should show the starting context, the observations made during the workflow, the action or recommendation rationale, and the final artifact that a domain owner can review.

The customer should be able to answer: what happened, which inputs mattered, what the system recommended, what changed over time, what risks or exceptions remain, and what a human team should do next.

## Evaluation Criteria

- Decision quality: confirm the recommendation is plausible for the observed state, customer constraints, and available actions.
- Scenario sensitivity: verify that outputs change appropriately when inputs, thresholds, seed values, or operating assumptions change.
- State trajectory: inspect whether `median_price_index`, `demand_index`, `cap_rate_pct`, `risk_score`, `liquidity_score`, and `rent_growth_signal` move coherently across the workflow rather than appearing as disconnected summaries.
- Traceability: confirm every recommendation can be tied back to inputs, events, intermediate decisions, and final artifact fields.
- Human review fit: check whether the artifact matches the language, evidence, and next-step format the target team already uses.
- Operational readiness: validate latency, reliability, adapter behavior, permissions, privacy, and approval gates before using real customer data.
- Outcome measurement: compare recommendations against historical cases, expert review, known policies, or measured business outcomes.

## Result Artifacts To Inspect

Inspect the event stream for observations, decisions, errors, and handoffs. Inspect the result payload and final artifact for the recommended action, ranked options or findings, supporting rationale, state changes, and next steps.

When using the local run store, inspect `run.json`, `config.json`, `inputs.json`, `events.jsonl`, `result.json`, and `final_artifact.json`. These artifacts are the review surface for debugging the workflow, comparing scenarios, and deciding whether the blueprint is ready for a real adapter.

## Prototype Limits

The current blueprint is a product-facing template and may include mock data, deterministic simulation, simplified policies, placeholder integrations, or partial worker coverage. It is designed to show the customer problem, target workflow, and expected artifact even where production implementation still needs hardening.

Outputs are decision-support artifacts. They should not be treated as final financial advice, medical guidance, safety certification, compliance approval, or executable operating instruction without customer validation and human approval.

## Upgrade Path To Real Customer Use

Replace the synthetic history with MLS exports, county records, broker notes, rent comps, lender constraints, inspection summaries, insurance quotes, and prior decision outcomes. Add customer-specific policies, review gates, exception handling, retention rules, and monitoring dashboards. Calibrate the workflow against historical data and expert judgment, then track acceptance rate, correction rate, latency, incident reduction, cost impact, and other outcome metrics that prove whether the workflow is helping.

## Product Narrative

This shows memory as measurable decision-quality lift, which is a stronger wedge than a simple chat interface over real-estate data.
