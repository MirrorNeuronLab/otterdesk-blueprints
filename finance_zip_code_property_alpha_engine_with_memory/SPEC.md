# Zip Code Property Alpha Engine With Memory SPEC

## What We Want To Achieve

Build a measurable memory-assisted acquisition workflow that can recover old but decisive deal facts from noisy history. The target customer should be able to see whether optimized memory preserved decision quality, reduced context cost, and changed the recommendation for the right reasons.

## Customer Problem

Real-estate investors, acquisition analysts, property-tech teams, and diligence operators need to make acquisition decisions from noisy deal flow. The customer gap is memory: older broker notes, lender exceptions, rent comps, insurance facts, and inspection risks can be decisive, but they are easy to lose inside long histories and distracting current snapshots.

## Design Details

The blueprint seeds a large synthetic history for the target ZIP and distractor ZIPs, then runs a property-market decision loop. At each step it builds two handoff paths: an all-context baseline and an optimized memory packet with stable `source_refs`.

Both paths produce an acquisition decision. The benchmark scores action accuracy, property match, critical fact recall, risk awareness, token use, latency estimate, and budget pressure. The applied decision updates the simulated market state and writes a final acquisition recommendation.

## Input

The prototype accepts target ZIP, maximum acquisition price, memory mode, history size, noise event volume, memory selection limit, all-context token budget, all-context attention limit, deterministic seed, step count, and market state overrides.

The current action space is `submit_bid`, `negotiate_discount`, and `watchlist_only`. Memory can run in comparison mode, on mode, or off mode, while the benchmark compares full-history context against an optimized source-grounded memory packet.

For production use, the same contract should be fed by MLS or listing exports, broker notes, rent comps, permit data, lender constraints, insurance quotes, inspection summaries, operating history, prior bids, and investment committee outcomes.

## Output: Expected Customer Outcome

The expected customer outcome is a source-grounded acquisition recommendation that preserves the few old facts that actually affect bid quality. A useful run returns ranked property opportunities, recommended action, recommended property, rationale, source references, memory packet, full-context baseline, optimized-memory decision, and benchmark metrics.

The customer should be able to see whether the system remembered the facts that matter, whether those facts changed the bid/watchlist decision, and whether optimized memory preserved or improved decision quality while reducing context cost.

## Evaluation Criteria

- Action accuracy: compare `submit_bid`, `negotiate_discount`, or `watchlist_only` against the benchmark oracle or historical investment committee decision.
- Property match: verify the recommended property matches the best risk-adjusted opportunity, not only the most attractive current snapshot.
- Critical fact recall: confirm the memory packet keeps important older facts such as rent upside, DSCR exceptions, seller motivation, inspection quality, flood insurance, or roof risk.
- Risk awareness: check that negative facts are reflected in the recommendation and rationale.
- Source coverage: inspect `source_refs` to confirm claims are grounded in retrievable facts.
- Memory lift: compare optimized-memory quality score, action accuracy, token reduction ratio, latency estimate, and budget violation rate against the full-context baseline.
- Production readiness: validate against real deal outcomes, underwriting decisions, realized operating performance, and human reviewer acceptance.

## Result Artifacts To Inspect

Inspect `timeline` for observations, context packets, memory packets, decisions, benchmark rows, and state updates. Inspect `memory_comparison` and `benchmark` for full-context versus optimized-memory quality, action accuracy, token reduction, and quality gate status.

Inspect `final_artifact` for recommended action, recommended property ID, ranked options, source-grounded rationale, action history, state changes, benchmark summary, and next steps. When using the local run store, also inspect `run.json`, `config.json`, `inputs.json`, `events.jsonl`, `result.json`, and `final_artifact.json`.

## Prototype Limits

The current blueprint uses synthetic property history, synthetic noisy context, and a benchmark oracle built for repeatable evaluation. It is not a guarantee of investment return, valuation accuracy, financing availability, or deal execution quality.

The memory layer is in-blueprint and synthetic. Production use requires real memory storage, access controls, provenance rules, data freshness checks, and validation against actual acquisition outcomes.

## Upgrade Path To Real Customer Use

Replace synthetic facts with customer deal-flow and diligence feeds while preserving stable source IDs and `source_refs`. Calibrate memory selection, fact importance, scoring weights, and action thresholds against historical investment committee decisions.

Connect outputs to investment memo, approval, CRM, or deal pipeline systems. Track bid recommendation quality, reviewer acceptance, critical-fact recall, underwriting error reduction, time saved in diligence, and realized performance after acquisition.
