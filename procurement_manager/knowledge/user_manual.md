# Procurement Manager user manual

Compare purchase options and see what they may cost over time. Get a side-by-side review of supplier quotes, suitability, risks, and missing information to help you decide what to buy. Prepares recommendations for your review without contacting suppliers or placing orders.

## Inputs

- analysis: Company-approved numerical assumptions for landed cost, discounted lifecycle cash flow, risk-adjusted TCO, equivalent annual cost, productive-unit cost, scenarios, and cash/finance/lease comparison.
- budget: Optional landed-acquisition budget or price ceiling for comparison.
- constraints: Optional purchase constraints and must-have requirements.
- input_folder: Local folder containing a plain-text purchase request, incomplete research notes or public links, and optional supporting evidence.
- item_description: Optional structured fallback for the item, supplier quote, public listing, vehicle, route, or trip to study; purchase_request.txt is primary when present.
- location: Optional market, pickup, destination, or service location.
- output_folder: Default local output folder for generated artifacts and reports.
- priorities: Optional ranking priorities such as total cost, quality, speed, or flexibility.
- purchase_type: Optional structured fallback category; use property, rental_property, car, airline_ticket, computer, or custom. Plain-text intake may infer it.
- route: Optional origin and destination for airline or travel research.
- travel_dates: Optional travel dates or purchase timing.

## Outputs and review



Consult the published run results and their evidence before making decisions. Missing evidence does not establish that an event or condition did not occur.

## Role and limits

# Procurement Manager conversation guide

This guide describes the purchase review workflow, not live supplier availability or a current quote.

I can compare requirements, approved supplier evidence, quotes, landed costs, technical fit, risk, and lifecycle cost. Ask which suppliers meet a requirement, how an NPV total cost, risk-adjusted total cost, equivalent annual cost, or scenario range was computed, and which transaction terms or approvals remain. Those answers need the current comparison packet and its source dates.

If prices, quotes, or technical evidence are missing or stale, say what cannot be compared and which document or confirmation is needed. Do not invent a market price or claim a supplier passes a gate without evidence. I prepare a review-ready decision packet; I do not contact suppliers, accept terms, place an order, or pay.


## Supervision

Use `get_capabilities` for the current tools and their availability. Common MCP actions are implemented by the SDK. `start_run` starts new work, `pause_run` preserves a resumable run, `resume_run` continues it, and `stop_run` terminates it. Domain stop actions affect their named resource only. Accepted actions are not evidence of completion; use `get_operation_status`.

External mutations require a caller-generated `request_id`. Tool results use `mn.mcp.tool_result.v1` in `structuredContent`; keep workflow state inside `data` and poll a returned `operation_id` with `get_operation_status`. The runtime also publishes this installed manual through its MCP Skills manifest.
