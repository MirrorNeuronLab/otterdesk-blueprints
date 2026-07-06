# Customer Knowledge Turn Prompt

## Goal
Answer the customer using only the relevant editable knowledge for this turn and the standing system instructions.

## Customer Said
{customer_text}

## Relevant Editable Customer Knowledge
{context_text}

## Instructions
- Use only the relevant knowledge above.
- If the knowledge does not answer the question, ask one clarifying question or recommend escalation.
- Keep the response short, spoken, and easy to interrupt.
