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

## Heavy-asset numerical decision methods

Keep sourced facts, company planning assumptions, and calculated outputs in
separate fields. A supplier price, stock statement, warranty term, tax rate, or
technical limit needs a traceable source and timestamp. Utilization, loaded
labor, downtime, maintenance reserve, discount rate, useful life, and residual
value are company assumptions until an owner approves them.

Use these calculations when the required inputs exist:

- **Landed acquisition cost** = base purchase price + mandatory options + tax +
  freight + installation + internal acquisition/deployment labor + other
  unavoidable implementation cost. Apply the acquisition budget to this amount.
- **Financial NPV TCO** = landed acquisition cost + present value of recurring
  energy/fuel, maintenance, support, software, insurance, facilities, and other
  operating cash costs - present value of expected residual value.
- **Risk-adjusted NPV TCO** = financial NPV TCO + probability-weighted one-time
  loss + present value of recurring expected downtime, disruption, failure, or
  compliance exposure. Never call a worst-case loss an expected cost unless a
  supported probability has been applied.
- **Equivalent annual cost (EAC)** = risk-adjusted NPV TCO multiplied by the
  capital-recovery factor. Use EAC to compare options with a common service
  requirement and analysis horizon; do not compare unequal service levels
  without an explicit normalization.
- **Cost per productive unit** = lifecycle cost divided by credible productive
  hours, miles, cycles, units, or transactions. State the denominator and do not
  divide by nameplate capacity when real utilization is the decision driver.
- **Incremental NPV, benefit-cost ratio, IRR, or payback** may be added only when
  the business supplies a defensible baseline and cash benefits. Cost savings,
  avoided cloud spend, capacity value, or labor benefits must not be invented.

Run at least low, base, and stress cases for the variables most likely to reverse
the ranking: utilization, energy/fuel, maintenance, downtime, useful life,
residual value, financing rate, delivery delay, and output. Identify the break-
even variable when a decision is close. A single precise TCO without sensitivity
is not a robust heavy-asset decision.

Compare acquisition structures on present-value economics and risk allocation:

- **Cash purchase:** purchase cash outflow, working-capital impact, ownership of
  residual value, and maintenance/obsolescence exposure.
- **Financed purchase:** down payment, financed principal, APR or effective rate,
  term, fees, payment timing, security interest, prepayment terms, tax treatment,
  and ownership of residual value.
- **Lease:** upfront payment, periodic payment, term, escalation, maintenance and
  insurance responsibility, usage limits, return condition, early termination,
  renewal, and end-of-term buyout or residual guarantee.
- **Rental, subscription, or managed service:** committed term, usage charges,
  minimums, included maintenance/support, service levels, cancellation, data or
  transition cost, and no-residual-value treatment.

Do not compare advertised monthly payments. Normalize each eligible structure to
present-value cost, equivalent annual cost, service level, usage, and risk. Mark
a method `not modeled` when complete real transaction terms are unavailable.

## Property and rental property

Check ownership or lease terms, title or landlord identity, inspection evidence, insurance, taxes, utilities, HOA or service charges, maintenance, financing assumptions, flood or environmental exposure, tenant or occupancy facts, deposits, renewal terms, and exit or cancellation constraints. A rent estimate is not proof of achievable income. A listing is not an inspection. A seller or broker statement needs a source and human verification.

## Cars and vehicles

Check VIN or identity evidence, title status, mileage, accident history, open recalls, inspection, service records, battery or powertrain coverage, warranty exclusions, registration, taxes, dealer fees, financing APR, insurance, fuel or charging cost, maintenance, and return rights. A reliability claim without a source is not a verified fact. Do not recommend a vehicle as safe or roadworthy without qualified inspection evidence.

## Business computers and AI workstations

Use a time-stamped public listing as a research observation only. Treat a
refreshed written supplier quote for the exact configuration—not a product-
family page or a parts list—as the approval unit. Capture the source URL,
observation time, supplier, quote date and expiry when applicable, exact GPU and
VRAM, CPU, system RAM, storage, network, power supply, operating system,
physical form factor, delivery/setup scope, lead time, taxes, payment terms,
warranty, support response, and return process. Separate upfront quote total
from annual support, energy, software, deployment labor, network/electrical
changes, and post-warranty renewal costs.

The technical owner must confirm that the quoted configuration supports the
planned workload and operating environment. The purchasing workflow can flag
missing evidence, but it must not certify model performance, electrical safety,
security approval, compatibility, or vendor capacity. A price that fits the
budget does not override an unmet VRAM, memory, delivery, warranty, security,
or approval constraint.

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

The final report must include the recommendation, confidence, rationale, evidence used, source references, public-source status counts, risk flags, evidence gaps, next steps, approval checklist, and the human review boundary. For heavy assets it must also state the preferred option, landed-budget position, financial and risk-adjusted NPV TCO, EAC, productive-unit economics when a denominator exists, scenario range, acquisition-method status, hard-constraint outcome, and source-freshness or lead-time status. A high-confidence label is not allowed when critical fields are missing or the only sources are blocked, stale, or uncorroborated.
