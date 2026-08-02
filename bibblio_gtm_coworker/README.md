# Bibblio GTM Co-worker

Blueprint ID: bibblio_gtm_coworker

Business goal: Turn Bibblio into a profitable business.

This is one independent member of the bibblio-profitability-team collaboration group. It owns GTM discovery, seed-contact qualification, partnerships, and draft outreach. It can run by itself and can exchange bounded, aggregate goal work packets with the other Bibblio co-workers through explicit MCP peer configurations.

## Workflow

1. qualify_seed_contacts creates the aspect analysis and a durable work packet.
2. publish_gtm_outreach_queue publishes a final, approval-ready aspect packet.

Input: an approved adult-professional contact CSV with Name, Email, Category, Note, and Highlight columns.

Local working artifact: confidential_outreach_queue.json.
Final artifact: gtm_operating_packet.json.

## Control boundary

It never sends messages. Names, email addresses, source notes, and individual drafts stay in a confidential local run artifact and are excluded from MCP packets.

No co-worker owns workflow routing, retry, logical completion, or human approval. Those remain blueprint and Mirror Neuron Core responsibilities.

## Synthetic quick test

The default configuration uses examples/sample_inputs/edtech_contacts_sample.csv. All bundled records are synthetic_demo and must not be represented as Bibblio results.

Run from the blueprint catalog:

    mn blueprint run bibblio_gtm_coworker

To collaborate, supply explicit peer_mcp_servers and enable peer_reads_enabled. Each peer record is filtered to goal_id bibblio-profitable-business.

See SPEC.md and payloads/knowledge/gtm_playbook.md for the role contract.
