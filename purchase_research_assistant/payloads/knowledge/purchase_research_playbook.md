# Purchase Research Evidence And Review Playbook

Use this playbook as a retrieval-grounded checklist for researching any purchase. It is not a price guarantee, appraisal, legal opinion, financial plan, travel guarantee, mechanical inspection, or substitute for a qualified professional.

## Evidence hierarchy

- Prefer a user-supplied invoice, quote, listing, fare rule, inspection, warranty, lease, or official provider policy for item-specific facts.
- Use official public pages for current price, availability, taxes, fees, eligibility, cancellation, return, safety, recall, and coverage rules.
- Treat search snippets, reviews, marketplaces, forums, and seller claims as lower-confidence leads that require corroboration.
- Preserve the source URL, source type, retrieval timestamp, and whether a fact is observed, conflicting, blocked, stale, or unknown.
- Never convert an unavailable source into an assumed fact. Explicitly report `unknown`, `not found`, `blocked`, or `review required`.

## Cross-category review

Every packet should identify the purchase type, item or trip, location or route, timing, budget, priorities, must-have constraints, and decision horizon. Separate the asking price from taxes, fees, financing, insurance, maintenance, subscriptions, deposits, baggage, cancellation, exchange-rate, delivery, or ownership costs. State which cost components are observed and which are missing.

For any purchase, start with need-fit and decision horizon, then build a decision frame covering must-haves, deal-breakers, alternatives, one-time cost, recurring and contingent cost, lifecycle or exit cost, quality, durability, reliability, safety, compatibility, accessibility, privacy, security, policy, warranty, returns, support, seller/provider risk, timing, logistics, eligibility, and regulatory obligations. Skip only dimensions that are genuinely not applicable and say why. Compare options only on fields that are actually comparable. Keep deterministic facts—prices, dates, distances, quantities, document hashes, fee totals, and source statuses—authoritative. LLM output may explain tradeoffs but must not overwrite those fields or invent a missing number.

## Property and rental property

Check ownership or lease terms, title or landlord identity, inspection evidence, insurance, taxes, utilities, HOA or service charges, maintenance, financing assumptions, flood or environmental exposure, tenant or occupancy facts, deposits, renewal terms, and exit or cancellation constraints. A rent estimate is not proof of achievable income. A listing is not an inspection. A seller or broker statement needs a source and human verification.

## Cars and vehicles

Check VIN or identity evidence, title status, mileage, accident history, open recalls, inspection, service records, battery or powertrain coverage, warranty exclusions, registration, taxes, dealer fees, financing APR, insurance, fuel or charging cost, maintenance, and return rights. A reliability claim without a source is not a verified fact. Do not recommend a vehicle as safe or roadworthy without qualified inspection evidence.

## Airline tickets and travel

Check the fare basis, taxes, carrier, airports, schedule, connection risk, baggage, seat, change, cancellation, refund, credit, expiration, visa or entry requirements, accessibility, and disruption rules. Prices and availability are volatile; every web observation must include a retrieval time and a warning that the user should recheck at decision time. Do not book or hold a fare.

## Recommendation labels

- `buy`: available evidence supports proceeding to human review, with no material unresolved blocker found.
- `consider`: the option may fit, but tradeoffs or evidence gaps remain.
- `wait`: timing, volatility, missing verification, or unresolved cost/risk makes immediate action premature.
- `avoid`: a material conflict, unsupported claim, policy issue, or stated constraint failure is present.
- `insufficient_evidence`: the packet lacks enough item-specific evidence to compare responsibly.

These labels are decision-support language only. The workflow must never buy, book, pay, submit an offer or application, or contact a seller, provider, broker, landlord, dealer, or airline.

## Public research boundaries

Construct queries only from the purchase type, sanitized item description, public location or route, timing, and non-confidential constraints. Never send raw local documents, account numbers, private financials, passwords, customer names, or contact details to public research. Use the lightweight text browser first and a rendered browser only when a public page requires it. Respect robots, login walls, rate limits, and CAPTCHAs; record the block rather than bypassing it.

## Output quality

The final report must include the recommendation, confidence, rationale, evidence used, source references, public-source status counts, risk flags, evidence gaps, next steps, and the human review boundary. A high-confidence label is not allowed when critical fields are missing or the only sources are blocked, stale, or uncorroborated.
