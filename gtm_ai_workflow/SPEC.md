# GTM AI Workflow SPEC

## What We Want To Achieve

Build a long-running GTM AI service that turns market signal into useful action: find target accounts, research each account, identify likely pain, draft personalized outreach, track responses, prepare sales email follow-up, summarize replies, update a local CSV CRM, recommend the next action, and feed insight back to product and marketing.

## Customer Problem

Many GTM teams use AI as a copy generator, but the higher-value problem is the learning loop. Account signals, outbound hypotheses, reply language, CRM state, product objections, and marketing positioning often live in separate places. Teams lose the context that would make the next message, next conversation, and next positioning change better.

## Design Details

The blueprint is organized as a MirrorNeuron long-lived workflow with service-style scheduling, isolated specialist workers, structured events, and local artifacts. The main worker roles are account researcher, outreach copywriter, email designer, deliverability reviewer, control manager, GTM automation sender, inbox poller, and response summarizer.

The workflow keeps local state in SQLite for draft coordination and writes customer-facing operating state to CSV files. `crm.csv` is the local CRM. `market_insights.csv` is the product and marketing feedback log.

## Inputs

- `initial_customer_list` is optional and may include name, email, title, company, profile, tags, and account signals.
- `crm_csv_folder` is the folder where local CSV state is written.
- `test_mode_email` is optional. When present, delivery is redirected only to that internal recipient while the CRM still records the real target account.

## Expected Outputs

- Target-account research brief and likely-pain hypothesis.
- Personalized sales email draft and rendered HTML.
- Delivery attempt status with test-recipient override metadata.
- Response summary and recommended next action.
- Local `crm.csv` and `market_insights.csv` updates.
- Run-store artifacts including `events.jsonl`, `result.json`, and `final_artifact.json`.

## Evaluation Criteria

- Account relevance: target accounts and pain hypotheses should follow from supplied profile and signal data.
- Outreach quality: drafts should connect one signal to one likely pain and one low-friction next action.
- Test-mode safety: configured test recipient must receive the email instead of the real account.
- CRM correctness: account state, last subject, delivery status, response summary, likely pain, and next action should be written to `crm.csv`.
- Learning loop: repeated pain, reply, objection, and positioning signals should appear in `market_insights.csv`.
- Traceability: recommendations should be tied to inputs, events, drafts, delivery results, and reply summaries.

## Prototype Limits

The bundled prototype uses synthetic target accounts and local CSV files. Live email, inbox polling, and LLM behavior depend on configured credentials and provider availability. Outputs are decision-support artifacts and should be reviewed before production use.

## Upgrade Path To Real Customer Use

Connect a real account source, approved email provider, inbox provider, and CRM export folder. Add approval gates for regulated or high-value outreach. Calibrate pain hypotheses against historical replies and accepted meetings. Review `market_insights.csv` with product and marketing teams to improve ICP, messaging, proof, objection handling, and product roadmap feedback.
