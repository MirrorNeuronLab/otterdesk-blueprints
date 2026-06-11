# GTM AI Workflow

`Blueprint ID:` `gtm_ai_workflow`
`Category:` `Business`
`Type:` `Long-lived service`

## One-line value proposition

Run a GTM learning loop that finds target accounts, researches pain, drafts outreach, tracks replies, updates a local CSV CRM, and feeds market insight back to product and marketing.

## What it is

This blueprint coordinates account research, outreach copywriting, email preparation, deliverability checks, response monitoring, CRM CSV updates, and market insight capture. It is built as a long-lived service: the scheduler can keep cycling, the inbox poller can watch for replies, and the local CRM files remain the operating record.

The point is not just to write an email. The workflow preserves the loop from market signal to outreach to conversation to product insight to sharper positioning.

## Inputs

- Optional initial customer or target-account list with fields such as `name`, `email`, `title`, `company`, `profile`, tags, and account signals.
- Local folder where `crm.csv` and `market_insights.csv` should be written.
- Optional test-mode recipient. When set, outbound email goes only to that internal address while CRM rows still record the real target account.

## Outputs

- `crm.csv` with account state, last outreach status, response summary, likely pain, and recommended next action.
- `market_insights.csv` with pain signals, reply signals, positioning insight, and product/marketing feedback.
- Prepared sales email drafts, delivery attempts, response events, and run-store artifacts such as `events.jsonl`, `result.json`, and `final_artifact.json`.

## How it works

The service starts from supplied or bundled target accounts. Account research selects the next GTM action, identifies likely pain, and writes a CRM row. The copywriter and email designer prepare personalized outreach. Deliverability and control workers decide whether a draft can be sent. The sender uses the test-recipient override when configured, records the delivery outcome, and schedules another cycle when appropriate. Inbox workers summarize replies and append CRM and insight rows.

## How to run

From the catalog:

```bash
mn run gtm_ai_workflow
```

From this folder:

```bash
mn run --folder .
```

Useful local overrides:

```bash
export GTM_CRM_CSV_DIR=/tmp/mn_gtm_ai_workflow_crm
export GTM_TEST_EMAIL_TO=internal-test@example.com
```

## What to inspect

Check `crm.csv` for account state and next actions. Check `market_insights.csv` for product and marketing feedback. Then inspect the run store for event-level traceability and generated email artifacts.

## Limitations

Live email and inbox behavior depend on local credentials and provider availability. Start with test mode or dry-run mode before using real recipients.

## Local Documentation

- [SPEC](SPEC.md)
- [TERM](TERM.md)
- [License](LICENSE.md)
- [Manifest](manifest.json)
- [Default config](config/default.json)
