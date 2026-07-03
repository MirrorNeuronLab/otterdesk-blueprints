# VC Startup Research And Method Playbook

Use this playbook as the canonical knowledge source for VC Assistant actor reviews. The goal is better evidence-backed diligence commentary, not investment advice or final valuation.

## Source Order

1. Company website and public product pages.
2. Crunchbase organization pages or search results.
3. Founder public profiles and company social pages.
4. Funding, investor, accelerator, or press mentions.
5. Market-size, public-company, SEC, BLS, SBA, and industry context.
6. Competitor and comparable-company pages.

## Prompt Output Contract

- Research agents must return JSON with `thought_summary`, `tool_calls`, `evidence_gaps`, `rag_refs`, and `stop_reason`.
- Review actors must return JSON with `summary`, `findings`, `risks`, `evidence_gaps`, `rag_refs`, and `recommended_next_step`.
- When Redis knowledge RAG is required, every LLM output must cite at least one RAG `ref` from the supplied citations.
- Use each agent's specialist mission. Do not reuse a generic all-agent prompt when the job is identity, funding, market/comps, traction, rendered-page review, reconciliation, scoring review, audit, report writing, or batch indexing.
- No agent may issue pass, watch, reject, buy, sell, invest, or investment recommendation labels. The output is diligence support only.

## Browser Skills

- `w3m_browser_skill` is the primary lightweight browser for search result pages and text-readable public pages.
- `web_browser_skill` is the optional Playwright fallback for JavaScript-rendered public pages such as Crunchbase profiles.
- Keep `respect_robots` enabled for rendered browsing.
- Treat blocked, login-required, CAPTCHA, rate-limit, and robots responses as source facts to record. Do not bypass them.

## Adaptive Research Playbooks

Use the company packet to choose research lanes. Start with identity, funding, market, and traction for every company, then add focused lanes when public-safe signals appear.

### GitHub And Open Source

- Trigger: a GitHub URL, open-source claim, repository name, package link, SDK, API, or developer-docs signal.
- Inspect: public organization/repository pages, README content, release/package hints, language mix, recent activity wording, issues/discussions wording, stars/forks if visible, and links to docs or packages.
- Good evidence: maintained repositories, public releases, meaningful technical docs, clear product relationship, active ecosystem use, or credible open-source adoption.
- Weak evidence: empty repos, unrelated personal projects, stale README-only projects, fork-only activity, or pages that require login.
- Tool choice: fetch known GitHub URLs directly with `w3m_browser_skill`; use rendered browser only if the public page is empty or blocked in lightweight browsing.

### Technical Product Depth

- Trigger: docs, API, SDK, developer, package, app-store, prototype, infrastructure, model, data, hardware, or platform signals.
- Inspect: public docs, changelog/release pages, package registries, app-store listings, product pages, status pages, security pages, and technical blog posts.
- Good evidence: working docs, versioned packages, product screenshots, demos, integrations, active releases, supported SDKs, and clear user workflow.
- Weak evidence: generic claims without docs, demo-only landing pages, private beta pages, or unrelated package names.

### Founder And Company Background

- Trigger: founder names, public profile links, company profile links, accelerator mentions, hiring pages, or team claims.
- Inspect: public company pages, founder bios, LinkedIn/company pages, Crunchbase, accelerator pages, press bylines, and public talks.
- Good evidence: relevant operating history, prior exits, domain expertise, credible advisors, and stable public company identity.
- Weak evidence: only contact details, private social links, unverifiable bios, or profile pages hidden behind login.
- Privacy rule: never use founder contact details in queries or reports.

### Customer And Traction Proof

- Trigger: revenue, ARR, customer, pilot, partnership, retention, growth, launch, case-study, or logo claims.
- Inspect: customer pages, public case studies, press releases, integration pages, app reviews, marketplace listings, public usage examples, and partner directories.
- Good evidence: named public case studies, credible press/partner proof, app/package adoption signals, repeatable pricing, and clear launch history.
- Weak evidence: confidential customer names, unverified logos, vague “enterprise traction,” or local-only revenue claims.
- Privacy rule: do not search private customer names unless they are clearly public in the source material.

### Pricing And Business Model

- Trigger: pricing, subscription, usage, seat, transaction fee, gross margin, CAC, LTV, payback, sales motion, or revenue model signals.
- Inspect: public pricing pages, packaging pages, terms pages, marketplaces, plan limits, integration pricing, and buyer-segment messaging.
- Good evidence: clear buyer, packaging, monetization path, public pricing, usage metrics, and sales motion fit.
- Weak evidence: no buyer, no packaging, unsupported margin assumptions, or monetization entirely deferred.

### Market Mapping And Competitors

- Trigger: market, TAM, SAM, vertical, category, industry, competitor, comparable, public-company, or exit signals.
- Inspect: competitor pages, public-company pages, SEC/EDGAR context where relevant, SBA/BLS/industry sources, marketplaces, and category reports.
- Good evidence: named competitor set, category boundaries, market growth support, buyer alternatives, and comparable public/private signals.
- Weak evidence: generic large-market claims, unrelated public companies, or configured references with no company-specific source.

### Fundraising And Investor Signals

- Trigger: seed, pre-seed, Series A, investor, accelerator, grant, venture, round, SAFE, valuation, or runway signals.
- Inspect: Crunchbase/search snippets, investor portfolio pages, accelerator cohorts, press releases, founder announcements, and public grant/award pages.
- Good evidence: named round, investor, accelerator cohort, grant, or milestone with public source.
- Weak evidence: pitch-only fundraise targets, unverified investor logos, stale rumors, or paid-provider-only data not available to the run.

### Regulatory And Security Risk

- Trigger: HIPAA, SOC 2, GDPR, compliance, privacy, security, healthcare, fintech, legal, education, government, insurance, or regulated-data claims.
- Inspect: security pages, trust centers, privacy policies, terms, compliance attestations, public regulatory guidance, and industry risk context.
- Good evidence: clear compliance scope, public policy pages, certifications or attestations, and credible data-handling claims.
- Weak evidence: compliance buzzwords without public artifacts, missing privacy policy, or ambiguous regulated-data use.

### Data, IP, And Defensibility

- Trigger: patent, proprietary data, dataset, model, algorithm, workflow lock-in, integration network, hardware design, or trade-secret claims.
- Inspect: public patent search pages when available, docs, research posts, technical blogs, product architecture claims, integrations, and data-source descriptions.
- Good evidence: defensible dataset access, technical moat, protected IP, integration depth, hard-to-replicate workflows, or public patent/application signals.
- Weak evidence: generic AI/model claims, unproven proprietary data, unsupported patent claims, or commodity wrapper functionality.

## Tool Selection Rules

- Use lightweight browser search for broad discovery and query expansion.
- Use direct page fetch when the packet contains a public URL, domain, GitHub repo, docs page, package page, app-store page, profile page, or pricing page.
- Use rendered browser only for JavaScript-heavy public profile pages, known rendered pages, or lightweight-browser results that are empty, blocked, or login-shaped.
- Record the reason a lane was selected and preserve blocked/empty outcomes as evidence.
- Label source quality as one of: `local_claim`, `public_confirmation`, `public_conflict`, `blocked`, `thin_signal`, `technical_signal`, or `market_context`.

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
