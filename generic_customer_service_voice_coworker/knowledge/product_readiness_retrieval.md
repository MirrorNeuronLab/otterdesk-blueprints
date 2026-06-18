# Customer Service Voice Retrieval Playbook

## Useful Retrieval Queries

- Which menu item, size, topping, price, pickup or delivery detail, and handoff policy supports the current caller response?
- Which caller requests require human handoff because they involve payment cards, refunds, allergies, complaints, emergencies, or unsupported custom work?
- What evidence should be preserved in the transcript before summarizing the order?

## Evidence Checklist

Use the menu knowledge, caller utterance, collected order fields, and handoff policy as the evidence source. Do not invent prices, availability, delivery eligibility, tax-inclusive totals, refund decisions, or allergy guarantees. If an order detail is missing, ask one focused question instead of guessing.

For review artifacts, preserve caller intent, item names, sizes, quantities, pickup or delivery mode, contact fields collected, unresolved questions, and any human handoff reason. Keep card numbers and sensitive payment details out of the transcript.

## Output Guidance

The final run summary should show the draft order or handoff state, evidence references, confidence, and next action for a human operator. Optional websocket event fan-out is disabled by default, so local run-store events and transcripts remain the authoritative output unless a live destination is configured.
