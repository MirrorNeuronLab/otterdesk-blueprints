# Code verifier manual

Choose a local repository checkout or source/docs folder in the first setup
question. No source folder is selected by default. Start a run. The
co-worker reads documentation, creates rules.md, asks you to approve the rules
in this conversation, verifies approved rules one by one, and
writes report.md with pass/fail/unknown, exact evidence and confidence 0–1.
It does not execute or edit repository code or tests.

**Rule documents** defaults to **Current requirements**. Changelog history,
evaluation reports, tutorial instructions and bare code examples are recorded
separately from obligations. Review their exclusions alongside the rules. A
requirement for an example remains scoped to that example. **Project docs** keeps
the broader document selection; **All captured docs** also includes generated
reports. Captured material remains available for audit, with its source role.
The extraction packet budget defaults to 512 (`review.max_extraction_packets`,
1–2048); it never truncates the selected documents to fit.

Before verification, open **Review rules** in this conversation. Search the list
of short titles and select a rule to read its complete Markdown and source.
Choose **Edit Markdown**, preview your changes, then **Save rule** to update its
title or statement. Edits apply to this run and open a fresh review; saving never
approves the rules. Save or discard an open edit before approving.
**Approve all** confirms the entire saved list, including rules outside a search,
plus any displayed coverage gaps or investigation limits. **Reject** stops the
review. No reply or an unavailable review service never counts as approval.
The review expires after one hour by default. Approval applies only to the
current run, source capture and unchanged rules.

Add customized rules as Markdown files under this co-worker's Job knowledge
`rules/` folder, for example `rules/custom.md`. Each section has the form:

```markdown
## MY-RULE-ID — Short descriptive title

The software must enforce the stated condition.
```

Use one rule per heading, unique IDs (letters, digits, hyphens, underscores,
starting with a letter; 64 characters maximum), and no introductory prose.
Titles are optional and at most 120 characters. Use level-three or deeper
subheadings inside a rule. Exported rules.md retains titles and can be copied
into Knowledge to reuse changes from Chat.
`review.rules_mode=augment` adds these to extracted documentation rules. Retain
a generated GEN-... heading to override that rule. `review.rules_mode=replace`
verifies only your custom list; copy and edit the exported rules.md for this.
Save knowledge changes before starting a new run. An active run keeps its capture.

Pass requires scoped implementation evidence and independent review; Fail requires
a concrete contradictory source path and independent review.
Unknown means evidence is insufficient or an investigation could not finish.
Documentation, test definitions and missing search hits are not execution proof.
Confidence is an uncalibrated AI assessment, capped at 0.85 for static judgments.
Review cited source, omissions and limitations before making decisions.

The normal output folder is ~/Downloads/code-verifier, with each run
in its runtime-delivered timestamp folder. Rules, full structured results,
captured source, hashes, syntax coverage and investigations accompany report.md.
Open the completed run's web report in this conversation to inspect rule results
and evidence in the workspace.
Remote URLs are not fetched; clone first. Convert PDF/Word/image docs to UTF-8
Markdown before selection. Never include unauthorized source or secrets.

Standard MCP tools inspect manual, capability, current state and results. Reading
or asking a question never starts work. Explicit run controls start, pause, resume
or stop the bound Job using runtime-issued execution IDs. Core owns operations
and cancellation. Inspect operation completion before assuming a run finished.

The verifier uses offline ranked keyword search and syntax navigation, then reads
exact source spans. No extra model service or repository execution is required.
By default, each rule has six investigation calls plus a judgment and independent
critique (eight model calls total). Unknown results include a reason and next step;
the report distinguishes excluded requirements from verified coverage. A new
blueprint/prompt/analysis policy requires a fresh run and approval, preserving old
reports. This update does not require changes to Core, SDK or the desktop app.


## Stage-aware conversation

OtterDesk reads `payloads/prompts/conversation.json` as optional app-owned guidance. It combines this role and stage policy with the pending question, confirmed non-secret setup answers, recent dialogue, selected report and fresh Job state. Short follow-ups retain their topic; a correction does not silently change saved configuration.

Use Memory or explicitly ask to remember, edit or forget an explanation preference. This affects Chat wording only; working rules and evidence keep their existing domain controls. The optional `inputs.payload.supervisor_instructions` array is app-managed, never a required setup answer or a new workflow permission.

Use the selected run report and exact source/rule references. Documentation and absence of search hits cannot prove implementation correctness. Only Core approval of the exact rule revision authorizes verification. A conversational yes or saved preference cannot approve, edit or remove rules. Use Review rules and Job knowledge for requirements. Never execute repository code or claim conformance from missing evidence. Existing submitted runs retain their configuration, evidence and approvals. An idle prepared Job may refresh through the existing conditional API without rehiring, resetting memory or mutating an active run.
