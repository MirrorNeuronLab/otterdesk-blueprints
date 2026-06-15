# Startup Research Playbook

Use this playbook when the VC Assistant verifies startup packets with public web research.

## Source Order

1. Company website and public product pages.
2. Crunchbase organization pages or search results.
3. Founder public profiles and company social pages.
4. Funding, investor, accelerator, or press mentions.
5. Market-size, public-company, SEC, BLS, SBA, and industry context.
6. Competitor and comparable-company pages.

## Browser Skills

- `w3m_browser_skill` is the primary lightweight browser for search result pages and text-readable public pages.
- `web_browser_skill` is the optional Playwright fallback for JavaScript-rendered pages such as Crunchbase profiles.
- Keep `respect_robots` enabled for rendered browsing.
- Treat blocked, login-required, CAPTCHA, rate-limit, and robots responses as source facts to record. Do not bypass them.

## Privacy Rules

- Public queries may include company name, public domain, product category, and non-confidential public claims.
- Public queries must not include raw pitch-deck excerpts, private financials, customer names, founder contact details, or confidential diligence notes.
- Reports should distinguish local-document claims from public-source confirmations and conflicts.
