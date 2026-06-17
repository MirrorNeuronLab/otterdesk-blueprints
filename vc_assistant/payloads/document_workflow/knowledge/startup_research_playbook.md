# VC Startup Research And Method Playbook

Use this playbook as the canonical knowledge source for VC Assistant actor reviews. The goal is better evidence-backed diligence commentary, not investment advice or final valuation.

## Source Order

1. Company website and public product pages.
2. Crunchbase organization pages or search results.
3. Founder public profiles and company social pages.
4. Funding, investor, accelerator, or press mentions.
5. Market-size, public-company, SEC, BLS, SBA, and industry context.
6. Competitor and comparable-company pages.

## Browser Skills

- `w3m_browser_skill` is the primary lightweight browser for search result pages and text-readable public pages.
- `web_browser_skill` is the optional Playwright fallback for JavaScript-rendered public pages such as Crunchbase profiles.
- Keep `respect_robots` enabled for rendered browsing.
- Treat blocked, login-required, CAPTCHA, rate-limit, and robots responses as source facts to record. Do not bypass them.

## Privacy Rules

- Public queries may include company name, public domain, product category, and non-confidential public claims.
- Public queries must not include raw pitch-deck excerpts, private financials, customer names, founder contact details, or confidential diligence notes.
- Reports should distinguish local-document claims from public-source confirmations and conflicts.

## VC Method Knowledge

### Berkus Method

- Memory hook: Berkus = 5 buckets.
- Use case: quick pre-revenue value proxy based on risk reduction.
- Core question: has the startup reduced risk across sound idea, prototype, quality management team, strategic relationships, and product rollout or sales?
- Strong evidence: product/prototype proof, team credibility, customer or pilot signal, strategic distribution, market need.
- Missing evidence: no proof of product, no team detail, no rollout or sales signal, no strategic relationship evidence.
- Assumption rule: bucket scores are evidence-strength indicators only; do not present them as a dollar valuation unless a separate, supported valuation model exists.

### Scorecard / Bill Payne Method

- Memory hook: Scorecard = weighted comparison.
- Use case: compare a startup against similar early-stage startups using weighted factors.
- Core question: does this company look stronger or weaker than a comparable startup on team, market, product, traction, competition, and financing need?
- Strong evidence: founder quality, market size, product progress, traction, defensibility, capital plan, credible comparable context.
- Missing evidence: no peer set, no market benchmark, no traction detail, no capital need, or only default filler inputs.
- Assumption rule: default weights are acceptable for screening, but the report must name them and say they should be calibrated by fund strategy.

### Risk Factor Summation Method

- Memory hook: Risk Factor = risk checklist.
- Use case: adjust a baseline view for major risk categories.
- Core question: which risks are evidenced, which are unknown, and how should they affect diligence priority?
- Strong evidence: explicit risks across management, stage, legislation, manufacturing, sales, funding, competition, technology, litigation, international, reputation, and exit.
- Missing evidence: risk categories with no source-backed support should stay unknown rather than neutral-positive.
- Assumption rule: risk adjustments are directional diligence prompts, not price recommendations.

### VC Method

- Memory hook: VC Method = exit-return math.
- Use case: test whether a deal could generate venture-style returns.
- Core question: what exit value, ownership, investment amount, and required return multiple would be needed for the investment to work?
- Strong evidence: revenue, growth, market size, comparable exit or multiple, expected financing amount, expected ownership, exit timing.
- Missing evidence: no credible monetary input, no exit assumption, no return multiple, no ownership or dilution assumption.
- Assumption rule: any exit multiple, holding period, ownership, dilution, or return target must be named as an assumption with the evidence gap it covers.

### First Chicago Method

- Memory hook: First Chicago = scenario weighting.
- Use case: combine downside, base, and upside cases into a probability-weighted view.
- Core question: what value or score is implied if the company underperforms, performs as expected, or outperforms?
- Strong evidence: traction, market size, revenue or cost data, growth indicators, scenario-specific risks, probability rationale.
- Missing evidence: no monetary evidence, no traction evidence, no scenario probabilities, or no basis for downside/base/upside separation.
- Assumption rule: scenario probabilities are defaults unless source-backed; the report must label default probabilities as assumptions.

### Comparable Transactions / Market Multiples

- Memory hook: Comps = market benchmark.
- Use case: compare the startup with similar public companies, private financings, exits, or market multiples.
- Core question: what market evidence anchors this company against similar companies or transactions?
- Strong evidence: named comparable companies, domains, transaction or financing references, public-company context, revenue/multiple hints, category match.
- Missing evidence: no comparable source, no market benchmark, no transaction context, or sources that are blocked or only planned.
- Assumption rule: public snippets are screening evidence, not a private transaction database; mark thin comparable evidence as insufficient.

### Cost-to-Duplicate Method

- Memory hook: Cost-to-Duplicate = replacement cost.
- Use case: estimate what it would cost to rebuild the startup's asset base.
- Core question: what would it cost to reproduce the product, technology, data, IP, engineering work, regulatory work, or operational assets?
- Strong evidence: built product, prototype, patents, R&D spend, datasets, hardware, infrastructure, engineering headcount, elapsed build time.
- Missing evidence: no asset detail, no build-cost data, no team/time estimate, no IP or technical scope.
- Assumption rule: replacement cost is a floor proxy and misses upside; never treat it as full enterprise value.

## Judge Rubric For Actor Reviews

Score the report quality by looking for these dimensions:

- Method correctness: the method is applied for its intended purpose and does not drift into another valuation method.
- Evidence grounding: every score, status, warning, and assumption points to evidence refs or clear missing-evidence reasons.
- Assumption clarity: assumptions are named, bounded, and tied to the evidence gap they compensate for.
- Missing-evidence honesty: thin, default, blocked, or unavailable evidence is not treated as confirmation.
- Financial reasoning quality: monetary values, multiples, scenarios, exits, and rebuild costs are labeled as screening math rather than final valuation.
- Report usefulness: a human reviewer can see what to review next without receiving pass, watch, reject, buy, sell, invest, or recommendation labels.

## Actor Review Rules

- Use this playbook over generic startup, product, or unrelated domain knowledge.
- Treat deterministic method outputs as the source of numeric scores, then review whether the evidence and assumptions support them.
- When giving feedback, name the company, method, evidence gap, and suggested improvement whenever possible.
- If a method lacks evidence, praise neither the company nor the method result; state what source would be needed to improve confidence.
- Do not invent paid-provider data, private transaction comps, unobserved financials, founder claims, or customer proof.
