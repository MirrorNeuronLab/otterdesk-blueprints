# Purchase Intake And Research Planning Task

Before researching or recommending anything, build a structured procurement plan. The request can describe any good, service, property, vehicle, trip, subscription, or other purchase; do not force it into a narrow category.

Use the supplied request and local evidence to identify:

- the normalized purchase goal and likely category;
- explicit must-haves, deal-breakers, preferences, and decision horizon;
- the criteria that should be compared and how they should be weighted;
- the full-cost questions, including acquisition, implementation, recurring operating, maintenance, support, downtime, contingent, financing, tax, and exit/residual costs;
- the company assumptions required for numerical analysis: horizon, discount rate, utilization or output units, labor, energy/fuel, maintenance, downtime, insurance, residual value, and tax treatment as relevant;
- whether cash purchase, financed purchase, lease, rental, subscription, or another acquisition method is commercially available and economically comparable;
- the business outcome, decision owner, operating environment, and delivery deadline when present;
- the technical acceptance criteria, integration dependencies, security/privacy constraints, and lifecycle requirements when relevant;
- the supplier-commercial requirements: source freshness, written quote, tax treatment, delivery and setup scope, warranty, return terms, support, lead time, quote validity, and complete financing/lease terms when applicable;
- the approvals or subject-matter-owner checks that must happen before a purchase order;
- quality, safety, compatibility, policy, seller/provider, logistics, privacy, regulatory, and lifecycle questions that matter;
- public research questions that can be answered without private document text;
- missing facts that could materially change the decision.

Think broadly first, then prioritize the questions that could change the recommendation. Do not assume that a low sticker price is a low total cost, that a listing or review proves quality, or that a generic category rule applies to the specific item. Separate observed facts from company planning assumptions. Preserve uncertainty and ask for evidence rather than filling gaps.

Return only JSON with these keys:

```json
{
  "normalized_goal": "string",
  "category": "string",
  "must_haves": ["string"],
  "deal_breakers": ["string"],
  "decision_criteria": ["string"],
  "research_questions": ["string"],
  "public_query_topics": ["string"],
  "unknowns": ["string"],
  "technical_requirements": ["string"],
  "commercial_requirements": ["string"],
  "required_approvals": ["string"]
}
```

When the request is for office equipment, hardware, software, or a service, treat the exact purchasable configuration and its commercial terms as the unit of comparison. A time-stamped public listing can seed research, but it is not a reserved price, inventory commitment, or substitute for a written business quote. Do not treat a product family page, an advertised base price, or a generic checklist as proof that a supplier can deliver the requested configuration.

Never invent item-specific facts, prices, availability, terms, safety, security, compatibility, or legal requirements. Keep the output review-only.
