# Purchase Intake And Research Planning Task

Before researching or recommending anything, build a structured plan for the purchase decision. The request can describe any good, service, property, vehicle, trip, subscription, or other purchase; do not force it into a narrow category.

Use the supplied request and local evidence to identify:

- the normalized purchase goal and likely category;
- explicit must-haves, deal-breakers, preferences, and decision horizon;
- the criteria that should be compared and how they should be weighted;
- the full-cost questions, including recurring, contingent, and exit costs;
- quality, safety, compatibility, policy, seller/provider, logistics, privacy, regulatory, and lifecycle questions that matter;
- public research questions that can be answered without private document text;
- missing facts that could materially change the decision.

Think broadly first, then prioritize the questions that could change the recommendation. Do not assume that a low sticker price is a low total cost, that a listing or review proves quality, or that a generic category rule applies to the specific item. Preserve uncertainty and ask for evidence rather than filling gaps.

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
  "unknowns": ["string"]
}
```

Never invent item-specific facts, prices, availability, terms, safety, or legal requirements. Keep the output review-only.
