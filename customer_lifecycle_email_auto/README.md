# Customer Lifecycle Email Auto

`Blueprint ID:` `customer_lifecycle_email_auto`
`Category:` `Business`

## One-line value proposition

Plan, generate, review, send, and monitor lifecycle email campaigns from one governed workflow.

## What it is

This blueprint coordinates customer research, lifecycle copywriting, email design, deliverability checks, inbox monitoring, and campaign automation. The manifest uses the workflow-first blueprint contract with explicit input, output, runtime, and service registration metadata.

## Who this is for

It is for growth, lifecycle, and customer-success teams that need email outreach to react to customer state, campaign history, replies, and delivery constraints without turning every campaign into a one-off manual project.

It is designed to replace a static dashboard plus manual copy workflow when the team needs coordinated action, not just reporting.

## Why it matters

Lifecycle outreach is most valuable when it arrives at the right moment with the right context. Static templates miss reply signals, segment changes, policy checks, and delivery feedback that should shape each message.

A one-shot LLM prompt can draft a message, but it cannot reliably preserve state, run delivery checks, monitor replies, and leave behind auditable artifacts.

## Why this runtime is useful here

MirrorNeuron keeps each specialist worker isolated while sharing campaign context through the run store. That makes it easier to audit decisions, inspect generated artifacts, and keep human review and external delivery steps visible.

## How it works

The input adapter resolves mock, JSON, file, or environment-provided inputs. The workflow then fans out across research, writing, design, deliverability, control, automation, and inbox workers before writing `result.json` and `final_artifact.json` to the local run store.

## Example scenario

A lifecycle team wants to follow up with customers who showed interest in a product update. The blueprint reviews customer context, selects an appropriate campaign shape, drafts copy, checks the design and delivery plan, and records the final artifacts for review or delivery.

## Inputs

- Customer profile, segment, and activity history.
- Campaign objective, product context, and policy constraints.
- Optional reply context from AgentMail or another inbox source.
- Local overrides in `config/overwrite.json` for testing or environment-specific behavior.

## Outputs

- Campaign plan and customer brief.
- Draft subject, body, design metadata, and delivery recommendations.
- Delivery or dry-run status.
- Run artifacts under `~/.mn/runs/<run_id>/`, including `events.jsonl`, `result.json`, and `final_artifact.json`.

## How to run

From the catalog:

```bash
mn run customer_lifecycle_email_auto
```

From this folder:

```bash
mn run --folder .
```

Inspect recent run state:

```bash
mn blueprint monitor --follow
```

## How to customize it

Adjust `config/default.json` for reusable defaults and `config/overwrite.json` for local-only overrides. Review the worker payloads under `payloads/` when changing campaign logic, template selection, delivery behavior, or inbox handling.

## What to look for in results

Check whether the selected campaign matches the customer state, whether the copy references the right context, whether the design template fits the campaign type, and whether delivery actions stayed in dry-run or live mode as intended.

## Investor and evaluator narrative

This blueprint demonstrates how MirrorNeuron can coordinate a business workflow with multiple specialized agents, explicit runtime artifacts, human-readable traceability, and production-shaped service registration.

## Runtime features demonstrated

- Workflow-first manifest contract.
- Runtime worker bindings with HostLocal executor metadata.
- Local run-store artifacts for inspection and monitoring.
- Shared skill packaging across executor payloads.
- Optional external email, inbox, LLM, and Slack-adjacent configuration.

## Test coverage

The local tests cover shared skill imports, campaign template selection, reply-followup behavior, runtime input parsing, Slack channel defaults, and manifest runtime metadata. The catalog-level tests validate the blueprint manifest, documentation, bundle generation, and shared standard checks.

## Limitations

Live delivery and inbox behavior depend on local credentials and service availability. Start with mock or dry-run inputs before connecting customer data or external email providers.

## Next steps

Connect production-safe customer data sources, tune campaign policies for your organization, and add approval rules for any campaign type that should require a human decision before delivery.

## Local Documentation

- [SPEC](SPEC.md)
- [TERM](TERM.md)
- [License](LICENSE.md)
- [Manifest](manifest.json)
- [Default config](config/default.json)
